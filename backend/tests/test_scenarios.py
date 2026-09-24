"""P2 acceptance: all ten demo beats, in text mode, as one file.

This is the safety net for the live demo. If the microphone dies in the review
room, the pipeline below is the same one the panel will see, entered at the
transcript instead of at the audio.

The beats run in the order the runbook performs them, in one session, because
the session tier ratchet makes the order part of the behaviour under test.
"""
import json
import sqlite3

import pytest

from app import db, turn
from app.security import ledger

pytestmark = pytest.mark.slow

CUSTOMER = "CUST1000"


# The `live` fixture moved to conftest.py: test_call_state.py needs the same
# seeded database and a second copy of it would be a second thing to keep
# right.


@pytest.fixture(scope="module")
def session(live):
    voice = None
    if live.execute("SELECT 1 FROM speakers WHERE customer_id=?", (CUSTOMER,)).fetchone():
        voice = f"{CUSTOMER}_0.wav"
    out = turn.create_session(live, CUSTOMER, device_id="pytest-device", voice_clip=voice)
    return out


def ask(conn, session, text, **kw):
    return turn.run_turn(conn, session["session_id"], text=text, **kw)


# ---------------------------------------------------------------- beat 1

def test_beat_1_consent_is_the_first_ledger_entry(live, session):
    assert session["consent_ref"]
    assert "retention" in session["consent_notice"]["en"].lower() or \
           "days" in session["consent_notice"]["en"]
    row = live.execute("SELECT * FROM ledger WHERE idx=?", (session["ledger_index"],)).fetchone()
    assert row["kind"] == "consent"
    payload = json.loads(row["payload"])
    assert payload["consent_ref"] == session["consent_ref"]
    assert payload["retention_days"] > 0 and payload["purpose"]


# ---------------------------------------------------------------- beat 2

def test_beat_2_tier0_english_answered_from_policy(live, session):
    t = ask(live, session, "What are your home loan interest rates")
    assert t.intent == "product_info", t.intent
    assert t.risk_tier == 0, (t.risk_tier, t.risk_score, t.risk_components["raw"])
    assert t.decision == "automated", t.decision_reason
    assert t.retrieved, "nothing retrieved"
    top = t.retrieved[0]
    assert top.doc_id and top.version and top.score >= (t.retrieval_floor or 0)
    # Version awareness: the superseded 1.0 must not be the cited version.
    hl = [p for p in t.retrieved if p.doc_id == "POL-HL-001"]
    if hl:
        assert hl[0].version == "1.1", f"cited superseded version {hl[0].version}"
    # The identifier is NOT spoken: reading "P O L hyphen H L hyphen zero zero one"
    # at a customer is the most robotic thing the assistant did. The version is
    # said aloud and the exact id stays in the trace for the auditor.
    assert f"version {top.version}" in (t.reply_text or ""), t.reply_text
    assert top.doc_id not in (t.reply_text or "")
    assert t.action_result["doc_id"] == top.doc_id


# ---------------------------------------------------------------- beat 3

def test_beat_3_refusal_below_the_floor(live, session):
    t = ask(live, session, "What is the CEO's personal phone number")
    assert t.decision == "refused", (t.decision, t.decision_reason)
    assert t.retrieved == []
    assert t.retrieval_max_score is not None and t.retrieval_floor is not None
    assert t.retrieval_max_score < t.retrieval_floor, \
        (t.retrieval_max_score, t.retrieval_floor)
    reply = (t.reply_text or "").lower()
    assert "colleague" in reply or "agent" in reply, reply
    assert "not going to guess" in reply or "will not guess" in reply


# ---------------------------------------------------------------- beat 4

def test_beat_4_code_mixed_spans_and_cmi(live, session):
    t = ask(live, session, "Mera balance kitna hai, and last three transactions bhi bata do")
    langs = {s.lang for s in t.language_spans}
    assert len(langs) >= 2, (langs, [s.model_dump() for s in t.language_spans])
    assert t.code_mix_index and t.code_mix_index > 0
    assert t.intent in ("get_balance", "mini_statement"), t.intent
    stage = t.stage_named("langid")
    assert stage and stage.outputs["spans"] and stage.outputs["eta"] > 0


# ---------------------------------------------------------------- beat 5

def test_beat_5a_account_query_without_a_voice_check_does_not_proceed(live, session):
    """The fix for the bug the recording caught: the assistant used to score a
    seeded WAV off disk and report it as the caller's verification, so a tester
    reached account data without ever being checked."""
    t = ask(live, session, "What is my account balance")
    assert t.risk_tier >= 1
    assert t.auth is not None and t.auth.passed is False
    assert "no voice check" in (t.auth.reason or "")
    assert t.decision == "escalated"
    assert t.action_taken == "request_verification"
    assert t.auth.s_verify == 0.0


def test_beat_5b_tier1_proceeds_on_a_real_voice_check(live, session):
    out = turn.record_verification(live, session["session_id"], None, source="demo_clip")
    assert out["passed"] is True, out
    assert out["simulated"] is True, "the seeded-clip path must declare itself"
    assert 0.0 <= out["cosine"] <= 1.0 and out["cosine"] >= out["threshold"]

    t = ask(live, session, "What is my account balance")
    assert t.risk_tier >= 1
    assert t.auth is not None and t.auth.passed is True
    assert t.auth.speaker_score is not None, "no cosine recorded"
    assert t.auth.spoof_score is not None, "no anti-spoof score recorded"
    assert t.auth.s_verify == pytest.approx(t.auth.speaker_score * t.auth.spoof_score, abs=1e-3)
    assert t.risk_components["raw"]["verify"] == pytest.approx(1 - (t.auth.s_verify or 0), abs=1e-6)
    assert t.decision == "automated", t.decision_reason
    # A seeded-clip check is SIMULATED wherever it shows up.
    stage = t.stage_named("speaker_verify")
    assert stage and stage.capability == "SIMULATED"


def test_beat_5c_a_voice_check_expires(live):
    """A check is evidence about who is speaking now, so it runs out."""
    from app.config import VERIFICATION_MAX_TURNS
    s = turn.create_session(live, CUSTOMER, device_id="expiry", voice_clip=f"{CUSTOMER}_0.wav")
    assert turn.record_verification(live, s["session_id"], None, source="demo_clip")["passed"]
    for _ in range(VERIFICATION_MAX_TURNS):
        turn.run_turn(live, s["session_id"], text="What is my account balance")
    t = turn.run_turn(live, s["session_id"], text="What is my account balance")
    assert t.auth.passed is False
    assert "expired" in (t.auth.reason or "")


def test_missing_seeded_clip_is_reported_not_crashed(live):
    """Picking a customer with no seeded voice used to raise FileNotFoundError
    on the first account turn."""
    s = turn.create_session(live, "CUST1005", device_id="noclip",
                            voice_clip="CUST1005_0.wav")
    out = turn.record_verification(live, s["session_id"], None, source="demo_clip")
    assert out["passed"] is False and "no seeded clip" in out["reason"]
    t = turn.run_turn(live, s["session_id"], text="What is my account balance")
    assert t.decision == "escalated" and t.action_taken == "request_verification"


# ---------------------------------------------------------------- beat 6

def test_beat_6_tier2_requires_otp_then_readback(live, session):
    turn.record_verification(live, session["session_id"], None, source="demo_clip")
    t = ask(live, session, "Block my card ending 4321")
    assert t.intent == "block_card", t.intent
    assert t.risk_tier >= 2, (t.risk_tier, t.risk_score)
    assert t.decision == "escalated"
    assert "password" in (t.reply_text or "").lower() or "otp" in (t.reply_text or "").lower()
    assert t.auth and t.auth.otp_required

    wrong = turn.run_turn(live, t.session_id.__str__(), text="", otp="000000")
    assert wrong.auth.otp_passed is False and wrong.decision == "escalated"

    t2 = ask(live, session, "Block my card ending 4321")
    ok = turn.run_turn(live, str(t2.session_id), text="", otp="123456")
    assert ok.auth.otp_passed is True
    assert ok.action_taken == "readback", ok.action_taken
    assert "confirm" in (ok.reply_text or "").lower()
    # Read back digit by digit, because "the card ending four thousand three
    # hundred and twenty one" is not what a person says.
    assert ok.auth.readback_text
    assert "four three two one" in ok.auth.readback_text, ok.auth.readback_text

    done = turn.run_turn(live, str(t2.session_id), text="", confirm=True)
    assert done.decision == "automated", done.decision_reason
    assert done.action_taken == "block_card"
    card = live.execute("SELECT status FROM cards WHERE card_number LIKE '%4321'").fetchone()
    if card:
        assert card["status"] == "blocked"


def test_beat_6b_declining_the_readback_changes_nothing(live, session):
    turn.record_verification(live, session["session_id"], None, source="demo_clip")
    t = ask(live, session, "Increase my daily limit to fifty thousand")
    assert t.risk_tier >= 2
    turn.run_turn(live, str(t.session_id), text="", otp="123456")
    out = turn.run_turn(live, str(t.session_id), text="", confirm=False)
    assert out.decision == "refused"
    assert out.action_taken == "readback_declined"


# ---------------------------------------------------------------- beat 7

def test_beat_7_tier3_hard_override_and_handover(live, session):
    t = ask(live, session, "Someone has made a fraudulent transaction on my account")
    assert t.intent == "fraud_report", t.intent
    assert t.risk_tier == 3
    assert t.tier_overridden is True, "fraud report must bypass the score entirely"
    assert t.decision == "escalated"
    assert t.action_taken == "escalate_to_agent"
    assert t.handover_packet_ref, "no context packet was queued"
    row = live.execute("SELECT packet FROM handovers WHERE handover_id=?",
                       (t.handover_packet_ref,)).fetchone()
    packet = json.loads(row["packet"])
    assert packet["no_automated_action_taken"] is True
    assert len(packet["conversation"]) >= 1, "the agent must receive the prior turns"
    assert packet["risk_tier"] == 3


def test_beat_7b_ratchet_holds_for_account_access_but_not_public_information(live, session):
    """The ratchet stops an attacker lowering their own risk before touching an
    account. It must not stop the bank quoting its own published rates.

    Both halves matter. The first build had only the first half, and a single
    misheard turn then made the assistant refuse public information for the
    rest of the call.
    """
    public = ask(live, session, "What are your home loan interest rates")
    assert public.risk_tier == 0, "public information must not be held by the ratchet"
    assert public.decision == "automated"
    assert public.risk_components["tiering"]["ratchet_applies"] is False

    account = ask(live, session, "What is my account balance")
    assert account.risk_tier >= 3, "the ratchet must still hold for account access"


# ---------------------------------------------------------------- beat 8

def test_beat_8_pii_is_tokenised_and_the_turn_path_writes_no_plaintext_audio(live):
    """The turn path itself still holds query audio in memory only.

    Recordings are a separate, consent-gated, encrypted store (D21). The two
    tests that police it are test_persistence.py::test_no_unencrypted_audio_
    on_disk and ::test_audio_is_not_stored_without_consent. This one covers
    what it always covered: transcription leaves nothing behind.
    """
    from app.config import RUNTIME_DIR
    s2 = turn.create_session(live, CUSTOMER, device_id="pytest-device-2")
    t = turn.run_turn(live, s2["session_id"],
                      text="my card is 4539 5787 6362 1486 and my number is 9822012345")
    assert "4539" not in (t.transcript or ""), t.transcript
    assert "9822012345" not in (t.transcript or "")
    assert any(v == "CARD" for v in t.pii_tokens.values())

    stored = live.execute("SELECT body FROM traces WHERE trace_id=?",
                          (str(t.trace_id),)).fetchone()["body"]
    assert "4539578763621486" not in stored and "4539 5787 6362 1486" not in stored
    assert "9822012345" not in stored

    # The raw value is recoverable only from the encrypted vault.
    from app.security import crypto
    token = next(k for k, v in t.pii_tokens.items() if v == "CARD")
    assert crypto.vault_get(live, s2["session_id"], token).replace(" ", "") == "4539578763621486"

    leftovers = list(RUNTIME_DIR.rglob("*.wav")) + list(RUNTIME_DIR.rglob("*.raw"))
    assert leftovers == [], f"plaintext audio left on disk: {leftovers}"


# ---------------------------------------------------------------- beat 9

def test_beat_9_ledger_verifies_green(live):
    out = ledger.verify(live)
    assert out["ok"] is True, out
    assert out["records_checked"] > 0
    assert out["first_broken_index"] is None


# ---------------------------------------------------------------- beat 10

def test_beat_10_tamper_turns_the_chain_red_and_names_the_record(live):
    """The money shot. A plain SQL edit to one stored record, nothing else."""
    total = live.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]
    idx = total // 2
    row = live.execute("SELECT * FROM ledger WHERE idx=?", (idx,)).fetchone()
    original = row["payload"]
    payload = json.loads(original)
    payload["decision"] = "automated"
    payload["tampered_by"] = "a rogue database administrator"
    live.execute("UPDATE ledger SET payload=? WHERE idx=?",
                 (json.dumps(payload, sort_keys=True, separators=(",", ":")), idx))
    live.commit()
    try:
        out = ledger.verify(live)
        assert out["ok"] is False
        assert out["first_broken_index"] == idx, out
        assert out["broken_record_id"] == row["record_id"]
        assert out["broken_check"] == "binding"
        assert out["expected_hash"] != out["actual_hash"]
        # And the linear scan must agree, so the localisation is not a fluke.
        assert ledger.verify_linear(live)["first_broken_index"] == idx
    finally:
        live.execute("UPDATE ledger SET payload=? WHERE idx=?", (original, idx))
        live.commit()
    assert ledger.verify(live)["ok"] is True, "restore failed"


# ---------------------------------------------------------------- consent withdrawal

def test_consent_withdrawal_purges_and_records_the_purge(live):
    s3 = turn.create_session(live, CUSTOMER, device_id="pytest-device-3")
    turn.run_turn(live, s3["session_id"], text="my card is 4539 5787 6362 1486")
    assert live.execute("SELECT COUNT(*) c FROM vault WHERE session_id=?",
                        (s3["session_id"],)).fetchone()["c"] > 0

    out = turn.withdraw_consent(live, s3["session_id"])
    assert out["vault_rows_deleted"] > 0 and out["traces_deleted"] > 0
    assert live.execute("SELECT COUNT(*) c FROM vault WHERE session_id=?",
                        (s3["session_id"],)).fetchone()["c"] == 0
    assert live.execute("SELECT COUNT(*) c FROM traces WHERE session_id=?",
                        (s3["session_id"],)).fetchone()["c"] == 0

    purge = live.execute("SELECT * FROM ledger WHERE idx=?", (out["ledger_index"],)).fetchone()
    assert purge["kind"] == "purge"
    # The ledger survives the purge. It holds hashes and tokens, never
    # identifiers, and deleting it would destroy the proof that the purge ran.
    assert ledger.verify(live)["ok"] is True

    with pytest.raises(PermissionError):
        turn.run_turn(live, s3["session_id"], text="what is my balance")


def test_no_identifier_reaches_disk_as_a_number(live):
    """Regression. The slot parser once read a phone number as an amount, and
    a string-only redactor walked straight past the float on its way to disk."""
    s = turn.create_session(live, CUSTOMER, device_id="pytest-numeric")
    t = turn.run_turn(live, s["session_id"],
                      text="my number is 9822012345 and my card is 4539 5787 6362 1486")
    body = live.execute("SELECT body FROM traces WHERE trace_id=?",
                        (str(t.trace_id),)).fetchone()["body"]
    for identifier in ("9822012345", "4539578763621486", "4539 5787 6362 1486"):
        assert identifier not in body, f"{identifier} leaked into the stored trace"
    # And not through the float path either.
    assert "9822012345.0" not in body


def test_phone_number_is_never_parsed_as_an_amount():
    from app.pipeline import slots
    assert slots.parse_amount("my number is 9822012345") is None
    assert slots.extract("block my card ending 4321").get("amount") is None
