"""R1. Customers, voices, recordings and calls survive a restart.

The fault this covers: enrolling a real voice wrote one cache row and
nothing durable, so restarting the backend lost the customer and a caller
could not be recognised on a later call.

The other half is the recording rule reversal. Audio is now kept, which is
only defensible because the conditions are enforced here rather than
promised in a document.
"""
import sqlite3
from datetime import timedelta

import numpy as np
import pytest

from app import db, turn
from app.banking import registry
from app.config import RECORDING_RETENTION_DAYS
from app.security import crypto, recordings
from app.trace import utcnow


def tone(seed: int = 0, seconds: float = 1.0) -> bytes:
    from app.pipeline import audio_io
    rng = np.random.default_rng(seed)
    t = np.linspace(0, seconds, int(16000 * seconds), endpoint=False)
    sig = 0.3 * np.sin(2 * np.pi * (180 + seed * 40) * t) + 0.01 * rng.normal(size=t.size)
    return audio_io.to_wav_bytes(sig.astype(np.float32))


# ---------------------------------------------------------------- customers

def test_customer_is_created_with_a_masked_mobile(conn):
    c = registry.create_customer(conn, name="Test Caller", mobile="9822012345")
    assert c["mobile_masked"] == "XXXXXX2345"
    stored = conn.execute("SELECT phone FROM customers WHERE customer_id=?",
                          (c["customer_id"],)).fetchone()["phone"]
    assert stored == "XXXXXX2345"
    assert "9822012345" not in stored


def test_caller_identifies_by_mobile_or_customer_id(conn):
    c = registry.create_customer(conn, name="Test Caller", mobile="9822012345")
    assert registry.find_customer(conn, "9822012345")["customer_id"] == c["customer_id"]
    assert registry.find_customer(conn, c["customer_id"])["customer_id"] == c["customer_id"]
    assert registry.find_customer(conn, "9999999999") is None
    assert registry.find_customer(conn, "") is None


def test_an_ambiguous_last_four_identifies_nobody(conn):
    """Two customers sharing a last four must not silently resolve to one."""
    registry.create_customer(conn, name="A", mobile="9822012345")
    registry.create_customer(conn, name="B", mobile="9111112345")
    assert registry.find_by_mobile(conn, "9822012345") is None


# ---------------------------------------------------------------- enrolment

def test_the_embedding_is_encrypted_at_rest(conn):
    c = registry.create_customer(conn, name="Voice Owner")
    vec = np.random.default_rng(1).random(192).astype(np.float32)
    registry.save_enrollment(conn, c["customer_id"], vec, model_id="test", n_clips=3)
    row = conn.execute("SELECT embedding FROM voice_enrollments WHERE customer_id=?",
                       (c["customer_id"],)).fetchone()
    assert bytes(row["embedding"]) != vec.tobytes(), "embedding stored in the clear"


def test_enrolment_survives_a_cold_cache(conn):
    """The restart case, simulated by clearing the hot-path table."""
    c = registry.create_customer(conn, name="Voice Owner")
    vec = np.random.default_rng(2).random(192).astype(np.float32)
    registry.save_enrollment(conn, c["customer_id"], vec, model_id="test", n_clips=3)
    conn.execute("DELETE FROM speakers")
    conn.commit()
    restored = registry.load_enrollment(conn, c["customer_id"])
    assert restored is not None
    assert np.allclose(restored, vec)


def test_revoking_keeps_the_withdrawal_auditable_and_drops_the_embedding(conn):
    c = registry.create_customer(conn, name="Voice Owner")
    registry.save_enrollment(conn, c["customer_id"],
                             np.zeros(192, dtype=np.float32), model_id="t", n_clips=3)
    out = registry.revoke_enrollment(conn, c["customer_id"])
    assert out["revoked"] == 1
    row = conn.execute("SELECT revoked_at, embedding FROM voice_enrollments"
                       " WHERE customer_id=?", (c["customer_id"],)).fetchone()
    assert row["revoked_at"] and bytes(row["embedding"]) == b""
    assert registry.load_enrollment(conn, c["customer_id"]) is None


# ---------------------------------------------------------------- recordings

def _consented_call(conn, recording=True):
    s = turn.create_session(conn, "CUST1000", channel="browser",
                            recording_consent=recording)
    turn.complete_recording_notice(conn, s["session_id"], recording)
    return s


def test_audio_is_not_stored_without_consent(conn):
    """One of the two tests that replace the old no-raw-audio rule."""
    s = turn.create_session(conn, "CUST1000", recording_consent=False)
    with pytest.raises(recordings.ConsentError, match="notice"):
        recordings.store(conn, s["call_id"], tone(), speaker="customer")

    turn.complete_recording_notice(conn, s["session_id"], consented=False)
    with pytest.raises(recordings.ConsentError, match="consent"):
        recordings.store(conn, s["call_id"], tone(), speaker="customer")

    assert conn.execute("SELECT COUNT(*) c FROM recordings").fetchone()["c"] == 0


def test_no_unencrypted_audio_on_disk(conn, tmp_path, monkeypatch):
    """The other replacement test. Every stored byte must be ciphertext."""
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    audio = tone(3)
    out = recordings.store(conn, s["call_id"], audio, speaker="customer")

    on_disk = (tmp_path / "rec").glob("*")
    for f in on_disk:
        raw = f.read_bytes()
        assert not raw.startswith(b"RIFF"), f"{f.name} is a playable WAV on disk"
        assert audio not in raw, f"{f.name} contains the plaintext"
    assert out["sha256"]


def test_a_stored_recording_round_trips_for_a_compliance_officer(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    audio = tone(4)
    out = recordings.store(conn, s["call_id"], audio, speaker="customer")
    back = recordings.read(conn, out["recording_id"], actor="officer",
                           role="compliance_officer")
    assert back == audio


@pytest.mark.parametrize("role", ["customer", "agent"])
def test_only_compliance_can_play_a_recording(conn, tmp_path, monkeypatch, role):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    out = recordings.store(conn, s["call_id"], tone(5), speaker="customer")
    with pytest.raises(PermissionError):
        recordings.read(conn, out["recording_id"], actor="someone", role=role)
    denied = conn.execute(
        "SELECT action FROM access_log WHERE target_id=?",
        (out["recording_id"],)).fetchone()
    assert denied["action"] == "play_recording_denied"


def test_every_playback_is_logged_and_ledgered(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    out = recordings.store(conn, s["call_id"], tone(6), speaker="customer")
    recordings.read(conn, out["recording_id"], actor="officer", role="compliance_officer")
    recordings.read(conn, out["recording_id"], actor="officer", role="compliance_officer")

    plays = conn.execute(
        "SELECT COUNT(*) c FROM access_log WHERE action='play_recording'").fetchone()["c"]
    assert plays == 2
    led = conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE kind='recording_accessed'").fetchone()["c"]
    assert led == 2


def test_a_modified_recording_file_is_detected_on_playback(conn, tmp_path, monkeypatch):
    """The digest is of the plaintext, so an auditor knows they heard what
    was recorded."""
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    out = recordings.store(conn, s["call_id"], tone(7), speaker="customer")
    conn.execute("UPDATE recordings SET sha256='0'*64 WHERE recording_id=?",
                 (out["recording_id"],))
    conn.commit()
    with pytest.raises(ValueError, match="does not match its stored digest"):
        recordings.read(conn, out["recording_id"], actor="o", role="compliance_officer")


def test_withdrawing_consent_purges_the_recordings(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    out = recordings.store(conn, s["call_id"], tone(8), speaker="customer")
    from pathlib import Path
    assert Path(out["path"]).exists()

    turn.withdraw_consent(conn, s["session_id"])
    assert not Path(out["path"]).exists()
    row = conn.execute("SELECT purged_at FROM recordings WHERE recording_id=?",
                       (out["recording_id"],)).fetchone()
    assert row["purged_at"]
    assert conn.execute(
        "SELECT COUNT(*) c FROM ledger WHERE kind='recordings_purged'").fetchone()["c"] >= 1


def test_declining_the_notice_purges_what_was_already_captured(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn, recording=True)
    out = recordings.store(conn, s["call_id"], tone(9), speaker="customer")
    turn.complete_recording_notice(conn, s["session_id"], consented=False)
    from pathlib import Path
    assert not Path(out["path"]).exists()


def test_retention_purge_removes_only_expired_recordings(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    s = _consented_call(conn)
    fresh = recordings.store(conn, s["call_id"], tone(10), speaker="customer")
    old = recordings.store(conn, s["call_id"], tone(11), speaker="customer",
                           retention_days=-1)          # already past its window

    out = recordings.purge_expired(conn)
    assert out["purged"] == 1
    assert old["recording_id"] in out["recording_ids"]
    from pathlib import Path
    assert Path(fresh["path"]).exists() and not Path(old["path"]).exists()


def test_the_default_retention_window_is_ninety_days(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    assert RECORDING_RETENTION_DAYS == 90
    s = _consented_call(conn)
    out = recordings.store(conn, s["call_id"], tone(12), speaker="customer")
    from datetime import datetime
    until = datetime.fromisoformat(out["retention_until"])
    assert 89 <= (until - utcnow()).days <= 90


def test_enrolment_audio_is_kept_only_on_explicit_consent(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("app.security.recordings.ENROLMENT_AUDIO_DIR", tmp_path / "enr")
    out = recordings.store_enrolment_audio(conn, "ENR1", [tone(13)], consent=False)
    assert out["stored"] == 0
    assert not (tmp_path / "enr").exists()

    out = recordings.store_enrolment_audio(conn, "ENR2", [tone(14)], consent=True)
    assert out["stored"] == 1
    for f in (tmp_path / "enr").glob("*"):
        assert not f.read_bytes().startswith(b"RIFF")


# ---------------------------------------------------------------- calls

def test_a_session_belongs_to_a_persistent_call(conn):
    """R2 depends on this: before it, a session referenced a customer by a
    string that matched nothing durable, so customer lookup found nothing."""
    s = turn.create_session(conn, "CUST1000", channel="browser")
    assert s["call_id"]
    row = conn.execute("SELECT * FROM calls WHERE call_id=?", (s["call_id"],)).fetchone()
    assert row["customer_id"] == "CUST1000"
    assert row["channel"] == "browser"
    linked = conn.execute("SELECT call_id FROM sessions WHERE session_id=?",
                          (s["session_id"],)).fetchone()["call_id"]
    assert linked == s["call_id"]


def test_an_unidentified_call_binds_to_a_customer_by_stated_mobile(conn):
    c = registry.create_customer(conn, name="Late Caller", mobile="9822055555")
    s = turn.create_session(conn, None)
    assert conn.execute("SELECT customer_id FROM calls WHERE call_id=?",
                        (s["call_id"],)).fetchone()["customer_id"] is None

    out = turn.identify_caller(conn, s["session_id"], "9822055555")
    assert out["identified"] and out["customer_id"] == c["customer_id"]
    for table, key in (("sessions", s["session_id"]), ("calls", s["call_id"])):
        col = "session_id" if table == "sessions" else "call_id"
        assert conn.execute(f"SELECT customer_id FROM {table} WHERE {col}=?",
                            (key,)).fetchone()["customer_id"] == c["customer_id"]


def test_an_unmatched_identifier_does_not_guess(conn):
    registry.create_customer(conn, name="A", mobile="9822012345")
    registry.create_customer(conn, name="B", mobile="9111112345")
    s = turn.create_session(conn, None)
    out = turn.identify_caller(conn, s["session_id"], "9822012345")
    assert out["identified"] is False
    assert conn.execute("SELECT customer_id FROM calls WHERE call_id=?",
                        (s["call_id"],)).fetchone()["customer_id"] is None


def test_register_enrol_restart_call_in_and_get_verified(conn, tmp_path):
    """R1's acceptance criterion, end to end.

    Register a customer, enrol three clips, drop every connection and
    reopen the database, then call in anonymously, identify by the stated
    mobile number and get verified against the enrolment that was stored
    before the restart.

    The clips are the seeded voices rather than the `tone()` helper the rest
    of this file uses. A pure tone scores 0.01 on the anti-spoof baseline and
    is rejected, correctly, so it cannot demonstrate a passing verification.
    """
    from app.security import speaker
    path = tmp_path / "test.db"
    clips = [speaker.load_clip(f"CUST1000_{i}.wav") for i in range(3)]

    c = registry.create_customer(conn, name="Returning Caller", mobile="9822077777")
    cid = c["customer_id"]
    speaker.enrol(conn, cid, clips, "live")
    conn.close()

    # Restart: nothing in memory, only what reached the file.
    fresh = db.init_db(path)
    assert registry.find_customer(fresh, "9822077777")["customer_id"] == cid

    s = turn.create_session(fresh, None)
    assert turn.record_verification(fresh, s["session_id"], clips[0])["reason"] \
        == "session has no customer"

    ident = turn.identify_caller(fresh, s["session_id"], "9822077777")
    assert ident["identified"] and ident["enrolled"] and ident["next"] == "voice_verification"

    out = turn.record_verification(fresh, s["session_id"], clips[0])
    assert out["passed"], out
    assert out["simulated"] is False
    fresh.close()


def test_a_voice_turn_records_only_after_the_notice_and_consent(conn, tmp_path, monkeypatch):
    """The gate has to be on the live path, not only on the store function.

    Before this, every piece of R1's recording machinery existed and nothing
    in a real call ever called it.
    """
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    from app.security import speaker
    clip = speaker.load_clip("CUST1000_0.wav")

    s = turn.create_session(conn, "CUST1000")
    def stored():
        # purged_at is set rather than the row deleted: the tombstone is the
        # evidence that the purge happened.
        return conn.execute(
            "SELECT COUNT(*) c FROM recordings WHERE call_id=? AND purged_at IS NULL",
            (s["call_id"],)).fetchone()["c"]

    # No notice yet: the turn still runs, and nothing is kept.
    turn.run_turn(conn, s["session_id"], audio=clip)
    assert stored() == 0

    turn.complete_recording_notice(conn, s["session_id"], consented=True)
    turn.run_turn(conn, s["session_id"], audio=clip)
    assert stored() == 1

    # Withdrawing takes the kept audio with it.
    turn.withdraw_consent(conn, s["session_id"])
    assert stored() == 0
