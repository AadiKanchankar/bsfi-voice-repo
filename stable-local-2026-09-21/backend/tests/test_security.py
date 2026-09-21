"""Security properties that are not algorithms: encryption at rest, the
integrity of the vault boundary, and the no-raw-audio rule."""
import numpy as np
import pytest

from app.security import crypto


def test_aes_round_trip():
    nonce, ct = crypto.encrypt("4111111111111111", aad="sess-1")
    assert crypto.decrypt(nonce, ct, aad="sess-1") == "4111111111111111"
    assert b"4111" not in ct


def test_aad_binds_ciphertext_to_its_session():
    """A vault row moved to another session must not decrypt."""
    nonce, ct = crypto.encrypt("secret", aad="sess-1")
    with pytest.raises(Exception):
        crypto.decrypt(nonce, ct, aad="sess-2")


def test_nonce_is_never_reused():
    nonces = {crypto.encrypt("same plaintext", aad="s")[0] for _ in range(200)}
    assert len(nonces) == 200


def test_vault_holds_ciphertext_only(conn):
    crypto.vault_put(conn, "sess-1", "<CARD_1>", "CARD", "4111111111111111")
    row = conn.execute("SELECT * FROM vault").fetchone()
    assert b"4111" not in bytes(row["ciphertext"])
    assert crypto.vault_get(conn, "sess-1", "<CARD_1>") == "4111111111111111"
    # The dashboard view returns types, never values.
    assert crypto.vault_types(conn, "sess-1") == {"<CARD_1>": "CARD"}


def test_purge_removes_vault_and_traces(conn):
    crypto.vault_put(conn, "sess-1", "<CARD_1>", "CARD", "4111111111111111")
    conn.execute("INSERT INTO traces (trace_id, session_id, turn_index, created_at, body)"
                 " VALUES ('t1','sess-1',0,'now','{}')")
    conn.commit()
    out = crypto.purge_session(conn, "sess-1")
    assert out == {"vault_rows_deleted": 1, "traces_deleted": 1}
    assert crypto.vault_get(conn, "sess-1", "<CARD_1>") is None


def test_audio_decoding_never_writes_a_file(tmp_path, monkeypatch):
    """Raw audio lives in memory only. Decoding must not create a temp file."""
    from app.pipeline import audio_io
    monkeypatch.chdir(tmp_path)
    audio = (np.sin(np.linspace(0, 400, 16000)) * 0.4).astype(np.float32)
    wav = audio_io.to_wav_bytes(audio)
    decoded = audio_io.decode(wav)
    assert len(decoded) == len(audio)
    assert list(tmp_path.iterdir()) == []


def test_wav_round_trip_is_lossless_enough_for_verification():
    from app.pipeline import audio_io
    audio = (np.sin(np.linspace(0, 400, 16000)) * 0.4).astype(np.float32)
    back = audio_io.decode(audio_io.to_wav_bytes(audio))
    assert np.max(np.abs(back - audio)) < 1e-3
