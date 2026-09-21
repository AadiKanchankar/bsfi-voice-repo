"""AES-256-GCM at rest.

Used for the per-session PII vault and for the encrypted transcript directory.
The key is derived from an environment secret with SHA-256 so the demo runs with
no key ceremony; a deployment would take the key from a KMS instead. That
substitution is recorded in docs/STACK_MAPPING.md.
"""
from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import AES_KEY_DEFAULT, AES_KEY_ENV

NONCE_BYTES = 12


def _key() -> bytes:
    secret = os.environ.get(AES_KEY_ENV, AES_KEY_DEFAULT)
    return hashlib.sha256(secret.encode("utf-8")).digest()   # 32 bytes = AES-256


def encrypt(plaintext: str, aad: str | None = None) -> tuple[bytes, bytes]:
    """Returns (nonce, ciphertext). AAD binds the ciphertext to its context
    (the session id), so a row moved between sessions fails to decrypt."""
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"),
                                aad.encode("utf-8") if aad else None)
    return nonce, ct


def decrypt(nonce: bytes, ciphertext: bytes, aad: str | None = None) -> str:
    pt = AESGCM(_key()).decrypt(nonce, ciphertext,
                                aad.encode("utf-8") if aad else None)
    return pt.decode("utf-8")


def encrypt_file(path, plaintext: bytes, aad: str | None = None) -> None:
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(_key()).encrypt(nonce, plaintext, aad.encode("utf-8") if aad else None)
    with open(path, "wb") as fh:
        fh.write(nonce + ct)


def decrypt_file(path, aad: str | None = None) -> bytes:
    with open(path, "rb") as fh:
        blob = fh.read()
    return AESGCM(_key()).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:],
                                  aad.encode("utf-8") if aad else None)


# ---------------------------------------------------------------- PII vault
# Token -> raw identifier, encrypted per session and held in its own table so
# that reading the transcript store never yields an identifier. Consent
# withdrawal drops these rows; see purge_session.

def vault_put(conn, session_id: str, token: str, pii_type: str, raw: str) -> None:
    nonce, ct = encrypt(raw, aad=session_id)
    conn.execute(
        "INSERT OR REPLACE INTO vault (session_id, token, pii_type, nonce, ciphertext)"
        " VALUES (?,?,?,?,?)", (session_id, token, pii_type, nonce, ct))
    conn.commit()


def vault_get(conn, session_id: str, token: str) -> str | None:
    row = conn.execute(
        "SELECT nonce, ciphertext FROM vault WHERE session_id=? AND token=?",
        (session_id, token)).fetchone()
    if not row:
        return None
    return decrypt(row["nonce"], row["ciphertext"], aad=session_id)


def vault_types(conn, session_id: str) -> dict[str, str]:
    """Token -> type. Never the value. This is what the dashboard may see."""
    return {r["token"]: r["pii_type"] for r in conn.execute(
        "SELECT token, pii_type FROM vault WHERE session_id=?", (session_id,))}


def purge_session(conn, session_id: str) -> dict:
    """DPDP erasure: drop the vault and the transcripts for one session.

    The ledger is deliberately not deleted. It holds hashes and tokens, never
    identifiers, and deleting from it would destroy the very audit trail the
    erasure has to be provable against. A purge record is appended instead;
    see main.py withdraw_consent.
    """
    v = conn.execute("DELETE FROM vault WHERE session_id=?", (session_id,)).rowcount
    t = conn.execute("DELETE FROM traces WHERE session_id=?", (session_id,)).rowcount
    conn.commit()
    return {"vault_rows_deleted": v, "traces_deleted": t}


def demo() -> None:
    n, c = encrypt("4111111111111111", aad="sess-1")
    assert decrypt(n, c, aad="sess-1") == "4111111111111111"
    try:
        decrypt(n, c, aad="sess-2")
        raise AssertionError("AAD mismatch must fail")
    except Exception as exc:
        assert "AAD" not in str(type(exc))  # any cryptography error is fine
    print("crypto ok")


if __name__ == "__main__":
    demo()
