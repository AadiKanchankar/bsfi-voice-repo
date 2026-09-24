"""Call recording: consent-gated, encrypted, retained, and auditable.

Change Request 02 reverses the original rule that raw audio is dropped after
transcription. Real helplines record calls. The reversal is only defensible
if the conditions are enforced in code rather than promised in a document, so
each one has a function here and a test in tests/test_recordings.py:

  consent    `store` refuses unless the call has completed the recording
             notice AND the caller has not declined. There is no flag a
             caller can fail to notice: the default is not to record.
  encryption  every byte on disk is AES-256-GCM. `store` never writes
             plaintext, not even briefly to a temp file.
  retention   every row carries retention_until. `purge_expired` deletes the
             file and marks the row, and appends one ledger record.
  access      `read` is the only way back to plaintext, it takes an actor,
             and it writes an access-log row and a ledger record every time.

The digest stored is of the PLAINTEXT. That is deliberate: it lets an auditor
confirm that what they were played is what was recorded, which a ciphertext
digest cannot do (GCM nonces differ per write).
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import (ENROLMENT_AUDIO_DIR, RECORDING_RETENTION_DAYS,
                      RECORDINGS_DIR)
from ..trace import utcnow
from . import crypto, ledger


class ConsentError(PermissionError):
    """Raised when audio would be stored without a consented, noticed call."""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def call_may_record(conn: sqlite3.Connection, call_id: str) -> tuple[bool, str]:
    """Both conditions, checked against the row rather than trusted."""
    row = conn.execute(
        "SELECT notice_completed, recording_consent, ended_at FROM calls WHERE call_id=?",
        (call_id,)).fetchone()
    if row is None:
        return False, f"no call {call_id}"
    if not row["notice_completed"]:
        return False, "the recording notice has not finished playing"
    if not row["recording_consent"]:
        return False, "the caller has not consented to being recorded"
    return True, "consented and noticed"


def store(conn: sqlite3.Connection, call_id: str, audio: bytes, *,
          speaker: str, turn_id: int | None = None, language: str | None = None,
          consent_ref: str | None = None,
          retention_days: int = RECORDING_RETENTION_DAYS) -> dict:
    """Encrypt and store one clip. Raises ConsentError if it may not.

    The plaintext is hashed and encrypted in memory; it never reaches the
    filesystem in the clear.
    """
    allowed, why = call_may_record(conn, call_id)
    if not allowed:
        raise ConsentError(f"refusing to store audio for {call_id}: {why}")

    rec_id = f"REC{uuid.uuid4().hex[:12].upper()}"
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = RECORDINGS_DIR / f"{rec_id}.enc"
    digest = hashlib.sha256(audio).hexdigest()
    # AAD binds the ciphertext to its call, so a file moved between calls
    # fails to decrypt rather than silently playing under the wrong record.
    crypto.encrypt_file(path, audio, aad=call_id)

    now = utcnow()
    until = _iso(now + timedelta(days=retention_days))
    duration = _duration_s(audio)
    conn.execute(
        "INSERT INTO recordings (recording_id, call_id, turn_id, speaker, path,"
        " sha256, duration_s, language, consent_ref, created_at, retention_until)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (rec_id, call_id, turn_id, speaker, str(path), digest, duration, language,
         consent_ref, _iso(now), until))
    conn.commit()
    ledger.append(conn, "recording_stored", {
        "recording_id": rec_id, "call_id": call_id, "turn_id": turn_id,
        "speaker": speaker, "sha256": digest, "duration_s": duration,
        "retention_until": until, "consent_ref": consent_ref,
    }, session_id=call_id)
    return {"recording_id": rec_id, "path": str(path), "sha256": digest,
            "duration_s": duration, "retention_until": until}


def _duration_s(audio: bytes) -> float | None:
    try:
        from ..pipeline import audio_io
        from ..config import SAMPLE_RATE
        return round(len(audio_io.decode(audio)) / SAMPLE_RATE, 3)
    except Exception:                                   # noqa: BLE001
        return None


def read(conn: sqlite3.Connection, recording_id: str, *, actor: str,
         role: str) -> bytes:
    """Decrypt one recording. Compliance officers only, and always logged.

    The access check is here rather than only at the endpoint so that any
    future caller of this function inherits it.
    """
    if role not in ("compliance_officer", "admin"):
        log_access(conn, actor=actor, role=role, action="play_recording_denied",
                   target_type="recording", target_id=recording_id,
                   detail="role may not play recordings")
        raise PermissionError(f"role {role!r} may not play recordings")

    row = conn.execute("SELECT * FROM recordings WHERE recording_id=?",
                       (recording_id,)).fetchone()
    if row is None:
        raise KeyError(f"no recording {recording_id}")
    if row["purged_at"]:
        raise KeyError(f"recording {recording_id} was purged on {row['purged_at']}")

    audio = crypto.decrypt_file(row["path"], aad=row["call_id"])
    # Confirm the caller is hearing what was recorded, not a substituted file.
    digest = hashlib.sha256(audio).hexdigest()
    intact = digest == row["sha256"]

    log_access(conn, actor=actor, role=role, action="play_recording",
               target_type="recording", target_id=recording_id,
               detail=f"call={row['call_id']} intact={intact}")
    ledger.append(conn, "recording_accessed", {
        "recording_id": recording_id, "call_id": row["call_id"],
        "actor": actor, "role": role, "digest_matches": intact,
    }, session_id=row["call_id"])
    if not intact:
        raise ValueError(
            f"recording {recording_id} does not match its stored digest: the file "
            f"was modified after it was written")
    return audio


def purge_call(conn: sqlite3.Connection, call_id: str, reason: str) -> dict:
    """Delete every recording for a call. Used on consent withdrawal."""
    rows = list(conn.execute(
        "SELECT recording_id, path FROM recordings WHERE call_id=? AND purged_at IS NULL",
        (call_id,)))
    now = _iso(utcnow())
    for r in rows:
        Path(r["path"]).unlink(missing_ok=True)
        conn.execute("UPDATE recordings SET purged_at=? WHERE recording_id=?",
                     (now, r["recording_id"]))
    conn.commit()
    if rows:
        ledger.append(conn, "recordings_purged", {
            "call_id": call_id, "count": len(rows), "reason": reason,
            "recording_ids": [r["recording_id"] for r in rows], "purged_at": now,
        }, session_id=call_id)
    return {"call_id": call_id, "purged": len(rows), "reason": reason}


def purge_expired(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Retention enforcement. Safe to run repeatedly; intended as a cron job."""
    cutoff = _iso(now or utcnow())
    rows = list(conn.execute(
        "SELECT recording_id, call_id, path, retention_until FROM recordings"
        " WHERE purged_at IS NULL AND retention_until <= ?", (cutoff,)))
    stamp = _iso(utcnow())
    for r in rows:
        Path(r["path"]).unlink(missing_ok=True)
        conn.execute("UPDATE recordings SET purged_at=? WHERE recording_id=?",
                     (stamp, r["recording_id"]))
    conn.commit()
    if rows:
        ledger.append(conn, "retention_purge", {
            "count": len(rows), "cutoff": cutoff,
            "recording_ids": [r["recording_id"] for r in rows],
        })
    return {"purged": len(rows), "cutoff": cutoff,
            "recording_ids": [r["recording_id"] for r in rows]}


# ---------------------------------------------------------------- enrolment audio

def store_enrolment_audio(conn: sqlite3.Connection, enrollment_id: str,
                          clips: list[bytes], *, consent: bool) -> dict:
    """Keep the clips an enrolment was built from, only on an explicit yes.

    Separate directory from call recordings, as the change request requires:
    this is biometric source material, not a conversation, and it should not
    be reachable by a query that walks call recordings.
    """
    if not consent:
        return {"stored": 0, "reason": "no explicit consent to keep enrolment audio"}
    ENROLMENT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, clip in enumerate(clips):
        path = ENROLMENT_AUDIO_DIR / f"{enrollment_id}_{i}.enc"
        crypto.encrypt_file(path, clip, aad=enrollment_id)
        paths.append(str(path))
    ledger.append(conn, "enrolment_audio_stored", {
        "enrollment_id": enrollment_id, "clips": len(clips), "consent": True,
    })
    return {"stored": len(paths), "paths": paths}


# ---------------------------------------------------------------- access log

def log_access(conn: sqlite3.Connection, *, actor: str, role: str | None,
               action: str, target_type: str | None = None,
               target_id: str | None = None, detail: str | None = None) -> str:
    access_id = f"ACC{uuid.uuid4().hex[:12].upper()}"
    conn.execute(
        "INSERT INTO access_log (access_id, actor, role, action, target_type,"
        " target_id, detail, at) VALUES (?,?,?,?,?,?,?,?)",
        (access_id, actor, role, action, target_type, target_id, detail,
         _iso(utcnow())))
    conn.commit()
    return access_id
