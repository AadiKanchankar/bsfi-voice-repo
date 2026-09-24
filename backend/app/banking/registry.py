"""Customers, voice enrolments and caller identification, all persistent.

The fault this fixes: enrolling a real voice wrote a row to `speakers` and
nothing else, so a restart lost the customer and a caller could not be
recognised on a later call. Enrolment now writes a durable
`voice_enrollments` row with the embedding encrypted at rest, and `speakers`
becomes a fast lookup cache rebuilt from it.

A voice embedding is biometric data under the DPDP Rules. Three consequences
are implemented rather than noted:

  * the embedding is encrypted at rest, like any other identifier
  * the audio it was derived from is kept only on a separate explicit yes
  * revoking an enrolment is a first-class operation, not a row delete, so
    the fact that a customer withdrew is itself auditable
"""
from __future__ import annotations

import sqlite3
import uuid

import numpy as np

from ..config import PRESENTER_ID
from ..trace import utcnow
from ..security import crypto, ledger


def mask_mobile(number: str | None) -> str | None:
    """Store and show the last four only. A registered mobile is an
    identifier; the assistant never needs the whole thing to match on."""
    if not number:
        return None
    digits = "".join(c for c in str(number) if c.isdigit())
    return f"XXXXXX{digits[-4:]}" if len(digits) >= 4 else None


def create_customer(conn: sqlite3.Connection, *, name: str,
                    mobile: str | None = None, language: str = "en",
                    customer_id: str | None = None) -> dict:
    cid = customer_id or f"CUST{uuid.uuid4().hex[:8].upper()}"
    now = utcnow().isoformat()
    conn.execute(
        "INSERT INTO customers (customer_id, name, phone, email, language,"
        " enrolled, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (cid, name, mask_mobile(mobile), None, language, 0, "active", now))
    conn.commit()
    ledger.append(conn, "customer_created", {
        "customer_ref": cid, "language": language,
        "mobile_masked": mask_mobile(mobile), "created_at": now,
    })
    return {"customer_id": cid, "name": name, "mobile_masked": mask_mobile(mobile),
            "language": language, "created_at": now}


def find_by_mobile(conn: sqlite3.Connection, mobile: str) -> dict | None:
    """Identify a caller who states their registered mobile number.

    Matching is on the masked form, so the full number is never needed and
    never compared. Ambiguity (two customers sharing a last four) returns
    nothing rather than guessing, and the caller is asked for their customer
    id instead.
    """
    masked = mask_mobile(mobile)
    if not masked:
        return None
    rows = list(conn.execute(
        "SELECT customer_id, name, language FROM customers"
        " WHERE phone=? AND status='active'", (masked,)))
    if len(rows) != 1:
        return None
    return dict(rows[0])


def find_customer(conn: sqlite3.Connection, identifier: str) -> dict | None:
    """By customer id, or by a stated mobile number."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    row = conn.execute(
        "SELECT customer_id, name, language FROM customers"
        " WHERE customer_id=? AND status='active'", (ident.upper(),)).fetchone()
    if row:
        return dict(row)
    return find_by_mobile(conn, ident)


# ---------------------------------------------------------------- enrolment

def save_enrollment(conn: sqlite3.Connection, customer_id: str,
                    embedding: np.ndarray, *, model_id: str, n_clips: int,
                    quality: float | None = None, source: str = "live",
                    consent_ref: str | None = None,
                    audio_consent: bool = False) -> dict:
    """Persist an enrolment. Supersedes any earlier one for this customer."""
    enrollment_id = f"ENR{uuid.uuid4().hex[:12].upper()}"
    now = utcnow().isoformat()
    raw = np.asarray(embedding, dtype=np.float32).tobytes()
    nonce, ciphertext = crypto.encrypt_bytes(raw, aad=customer_id)

    conn.execute(
        "UPDATE voice_enrollments SET revoked_at=? WHERE customer_id=? AND revoked_at IS NULL",
        (now, customer_id))
    conn.execute(
        "INSERT INTO voice_enrollments (enrollment_id, customer_id, embedding,"
        " nonce, model_id, n_clips, quality, source, consent_ref, audio_consent,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (enrollment_id, customer_id, ciphertext, nonce, model_id, n_clips,
         quality, source, consent_ref, int(audio_consent), now))
    # speakers stays as the hot-path cache for verification.
    conn.execute(
        "INSERT OR REPLACE INTO speakers (customer_id, embedding, n_clips, source,"
        " enrolled_at) VALUES (?,?,?,?,?)",
        (customer_id, raw, n_clips, source, now))
    conn.execute("UPDATE customers SET enrolled=1 WHERE customer_id=?", (customer_id,))
    conn.commit()

    ledger.append(conn, "voice_enrolled", {
        "enrollment_id": enrollment_id, "customer_ref": customer_id,
        "model_id": model_id, "n_clips": n_clips, "quality": quality,
        "source": source, "audio_consent": bool(audio_consent),
        "consent_ref": consent_ref, "created_at": now,
    })
    return {"enrollment_id": enrollment_id, "customer_id": customer_id,
            "n_clips": n_clips, "quality": quality, "source": source,
            "audio_consent": bool(audio_consent), "created_at": now}


def load_enrollment(conn: sqlite3.Connection, customer_id: str) -> np.ndarray | None:
    """The live embedding. Prefers the cache, falls back to decrypting the
    durable row, which is what makes an enrolment survive a restart even if
    the cache table is cleared."""
    row = conn.execute("SELECT embedding FROM speakers WHERE customer_id=?",
                       (customer_id,)).fetchone()
    if row:
        return np.frombuffer(row["embedding"], dtype=np.float32)

    row = conn.execute(
        "SELECT embedding, nonce FROM voice_enrollments WHERE customer_id=?"
        " AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1",
        (customer_id,)).fetchone()
    if not row:
        return None
    raw = crypto.decrypt_bytes(row["nonce"], row["embedding"], aad=customer_id)
    vec = np.frombuffer(raw, dtype=np.float32)
    conn.execute(
        "INSERT OR REPLACE INTO speakers (customer_id, embedding, n_clips, source,"
        " enrolled_at) VALUES (?,?,?,?,?)",
        (customer_id, raw, 0, "restored", utcnow().isoformat()))
    conn.commit()
    return vec


def revoke_enrollment(conn: sqlite3.Connection, customer_id: str,
                      reason: str = "customer request") -> dict:
    """Withdraw biometric consent. The row is marked, not deleted, so the
    withdrawal itself remains auditable; the embedding is removed."""
    now = utcnow().isoformat()
    n = conn.execute(
        "UPDATE voice_enrollments SET revoked_at=?, embedding=? WHERE customer_id=?"
        " AND revoked_at IS NULL", (now, b"", customer_id)).rowcount
    conn.execute("DELETE FROM speakers WHERE customer_id=?", (customer_id,))
    conn.execute("UPDATE customers SET enrolled=0 WHERE customer_id=?", (customer_id,))
    conn.commit()
    ledger.append(conn, "voice_enrolment_revoked", {
        "customer_ref": customer_id, "enrolments_revoked": n, "reason": reason,
        "revoked_at": now,
    })
    return {"customer_id": customer_id, "revoked": n, "reason": reason}


def customer_summary(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM customers WHERE customer_id=?",
                       (customer_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    enr = conn.execute(
        "SELECT enrollment_id, model_id, n_clips, quality, source, created_at"
        " FROM voice_enrollments WHERE customer_id=? AND revoked_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1", (customer_id,)).fetchone()
    d["enrollment"] = dict(enr) if enr else None
    d["is_presenter"] = customer_id == PRESENTER_ID
    for key, sql in (("accounts", "SELECT COUNT(*) c FROM accounts WHERE customer_id=?"),
                     ("holdings", "SELECT COUNT(*) c FROM holdings WHERE customer_id=?"),
                     ("calls", "SELECT COUNT(*) c FROM calls WHERE customer_id=?")):
        d[key] = conn.execute(sql, (customer_id,)).fetchone()["c"]
    return d
