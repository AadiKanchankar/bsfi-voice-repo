"""R3. One turn at a time, and a reply that can be stopped.

The two faults: the caller could speak again before the reply finished and
get two overlapping voices and two replies, and once the assistant started
speaking there was no way to stop it. Both come from the client deciding when
a turn begins and ends, so the state moved to the server.

These tests assert the rules, not the implementation: exactly one active
turn, a superseded turn that stops and says so, a barge-in that records how
much was actually heard, and stop and end working from every state.
"""
import pytest

from app import call as callsm
from app import turn
from app.trace import ComplianceTrace


@pytest.fixture(autouse=True)
def _clean_registry():
    callsm.reset()
    yield
    callsm.reset()


@pytest.fixture()
def call(conn):
    s = turn.create_session(conn, "CUST1000")
    return s["call_id"], s["session_id"]


# ---------------------------------------------------------------- transitions

def test_the_machine_refuses_an_impossible_move(conn, call):
    """A call opens in GREETING: the consent notice is the greeting."""
    call_id, _ = call
    assert callsm.state(call_id)["state"] == callsm.GREETING
    with pytest.raises(callsm.BadTransition):
        callsm.transition(conn, call_id, callsm.SPEAKING)


def test_completing_the_notice_hands_the_floor_to_the_caller(conn, call):
    call_id, session_id = call
    turn.complete_recording_notice(conn, session_id, consented=True)
    assert callsm.state(call_id)["state"] == callsm.LISTENING


def test_every_state_can_end_and_nothing_follows_ending(conn, call):
    call_id, _ = call
    assert callsm.end_call(conn, call_id)["state"] == callsm.ENDED
    with pytest.raises(callsm.CallEnded):
        callsm.begin_turn(conn, call_id)
    with pytest.raises(callsm.CallEnded):
        callsm.interrupt(conn, call_id)


def test_ending_is_idempotent_and_writes_the_final_state(conn, call):
    call_id, _ = call
    callsm.end_call(conn, call_id, reason="caller hung up")
    assert callsm.end_call(conn, call_id)["state"] == callsm.ENDED
    row = conn.execute("SELECT ended_at, final_state FROM calls WHERE call_id=?",
                       (call_id,)).fetchone()
    assert row["ended_at"] and row["final_state"] == "caller hung up"


# ---------------------------------------------------------------- one turn

def test_turn_ids_increase_and_only_one_turn_is_active(conn, call):
    call_id, _ = call
    first_id, first = callsm.begin_turn(conn, call_id)
    assert first_id == 0
    assert callsm.state(call_id)["state"] == callsm.PROCESSING

    with pytest.raises(callsm.TurnInFlight):
        callsm.begin_turn(conn, call_id, supersede=False)

    second_id, second = callsm.begin_turn(conn, call_id)
    assert second_id == 1
    assert first.cancelled and not second.cancelled


def test_a_superseded_turn_is_recorded_rather_than_forgotten(conn, call):
    """Two rapid utterances must produce one reply, and an account of the
    other. Silently dropping it would leave a gap in the call."""
    call_id, _ = call
    callsm.begin_turn(conn, call_id)
    callsm.begin_turn(conn, call_id)
    row = conn.execute("SELECT decision, interrupted FROM turns"
                       " WHERE call_id=? AND turn_id=0", (call_id,)).fetchone()
    assert row["decision"] == "superseded" and row["interrupted"] == 1
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger")]
    assert "turn_superseded" in kinds


def test_a_cancelled_turn_stops_at_the_next_stage_boundary(conn, call):
    """Cooperative cancellation: the point is that it stops, not that it
    finishes and is discarded."""
    import uuid
    call_id, session_id = call
    _, token = callsm.begin_turn(conn, call_id)
    t = ComplianceTrace(session_id=uuid.uuid4(), turn_index=0,
                        consent_ref=uuid.uuid4())
    t._cancel = token
    with t.stage("first", "x"):
        pass
    token.cancel("caller spoke again")
    with pytest.raises(callsm.Cancelled):
        with t.stage("second", "x"):
            pytest.fail("the stage body must not run")
    assert [s.stage for s in t.stages] == ["first"]


def test_a_late_superseded_turn_does_not_drag_the_call_back(conn, call):
    """The turn that lost the race finishes last. It must not move the state."""
    call_id, _ = call
    old_id, _ = callsm.begin_turn(conn, call_id)
    new_id, _ = callsm.begin_turn(conn, call_id)
    callsm.finish_turn(conn, call_id, old_id)
    assert callsm.state(call_id)["state"] == callsm.PROCESSING
    callsm.finish_turn(conn, call_id, new_id)
    assert callsm.state(call_id)["state"] == callsm.SPEAKING


# ---------------------------------------------------------------- barge-in

def test_barge_in_records_how_much_was_actually_heard(conn, call):
    call_id, _ = call
    turn_id, _ = callsm.begin_turn(conn, call_id)
    callsm.finish_turn(conn, call_id, turn_id)
    assert callsm.state(call_id)["state"] == callsm.SPEAKING

    out = callsm.interrupt(conn, call_id, played_ms=420.0, played_chars=18,
                           reply_chars=90)
    assert out["state"] == callsm.LISTENING
    assert out["interrupted_from"] == callsm.SPEAKING
    assert out["fraction_delivered"] == 0.2

    payload = _last_ledger(conn, "interrupted")
    assert payload["played_ms"] == 420.0
    assert payload["fraction_delivered"] == 0.2
    assert conn.execute("SELECT interrupted FROM turns WHERE call_id=? AND turn_id=?",
                        (call_id, turn_id)).fetchone()["interrupted"] == 1


def test_stop_works_while_the_turn_is_still_processing(conn, call):
    call_id, _ = call
    _, token = callsm.begin_turn(conn, call_id)
    out = callsm.interrupt(conn, call_id, source="stop_button")
    assert token.cancelled
    assert out["state"] == callsm.LISTENING


def test_speaking_over_the_greeting_is_a_barge_in_not_an_error(conn, call):
    call_id, _ = call
    out = callsm.interrupt(conn, call_id)
    assert out["interrupted_from"] == callsm.GREETING
    assert out["state"] == callsm.LISTENING


# ---------------------------------------------------------------- the notice

def test_an_interrupted_notice_does_not_start_recording(conn, call, tmp_path,
                                                        monkeypatch):
    """`calls.notice_completed` is the single authority and an interrupted
    greeting never sets it, so storage keeps refusing."""
    monkeypatch.setattr("app.security.recordings.RECORDINGS_DIR", tmp_path / "rec")
    from app.security import recordings
    call_id, session_id = call
    callsm.interrupt(conn, call_id, source="barge_in")

    allowed, why = recordings.call_may_record(conn, call_id)
    assert not allowed and "notice" in why
    with pytest.raises(recordings.ConsentError):
        recordings.store(conn, call_id, b"RIFFfake", speaker="customer")

    # And once the notice has actually finished, with consent, it may.
    turn.complete_recording_notice(conn, session_id, consented=True)
    assert recordings.call_may_record(conn, call_id)[0]


def _last_ledger(conn, kind):
    import json
    row = conn.execute("SELECT payload FROM ledger WHERE kind=? ORDER BY idx DESC"
                       " LIMIT 1", (kind,)).fetchone()
    assert row is not None, f"no {kind} ledger record"
    return json.loads(row["payload"])


# ---------------------------------------------------------------- safety
#
# These need the seeded database: a tier 2 transfer needs a customer with an
# account and a payee, and an intent head that recognises the request. The
# `conn` fixture above is an empty migrated database, which is the right
# thing for the state machine tests and useless for these.


@pytest.fixture()
def live_call(live):
    # The seeded clip has to be attached at session creation: without it the
    # demo-clip verification has nothing to check, the caller stays
    # unverified, and a transfer lands at tier 3 as a mandatory handover
    # rather than at tier 2 with a read-back. Which is correct behaviour, and
    # not the behaviour under test here.
    voice = None
    if live.execute("SELECT 1 FROM speakers WHERE customer_id='CUST1000'").fetchone():
        voice = "CUST1000_0.wav"
    s = turn.create_session(live, "CUST1000", device_id="pytest-call",
                            voice_clip=voice)
    # These tests move real money in the demo database. Put it back.
    # Without this the account drains a little on every suite run and
    # eventually the transfer starts failing for insufficient funds, which
    # would look like a regression in the code rather than in the fixture.
    from app.banking.mock_core import MockCore
    acct = MockCore(live).primary_account("CUST1000")["account_id"]
    before = live.execute("SELECT balance FROM accounts WHERE account_id=?",
                          (acct,)).fetchone()["balance"]
    high_water = live.execute("SELECT COALESCE(MAX(rowid), 0) m"
                              " FROM transactions").fetchone()["m"]
    try:
        yield live, s["call_id"], s["session_id"]
    finally:
        live.execute("UPDATE accounts SET balance=? WHERE account_id=?",
                     (before, acct))
        live.execute("DELETE FROM transactions WHERE rowid > ?", (high_water,))
        live.commit()


def _debited_balance(conn):
    """The balance of the account a transfer actually debits.

    `fund_transfer` uses `MockCore.primary_account`, and CUST1000 has more
    than one account. Watching the wrong one made "no money moved" pass
    whether or not money moved, which is the least useful kind of green.
    """
    from app.banking.mock_core import MockCore
    acct = MockCore(conn).primary_account("CUST1000")
    return conn.execute("SELECT balance FROM accounts WHERE account_id=?",
                        (acct["account_id"],)).fetchone()["balance"]


def _reach_readback(conn, session_id):
    """Drive a tier 2 transfer as far as the spoken read-back."""
    from app.config import OTP_DEMO_CODE
    v = turn.record_verification(conn, session_id, None, source="demo_clip")
    assert v["passed"], v
    t = turn.run_turn(conn, session_id, text="transfer 5000 rupees to Diya")
    assert t.risk_tier == 2, f"expected tier 2, got {t.risk_tier}: {t.decision_reason}"
    turn.run_turn(conn, session_id, otp=OTP_DEMO_CODE)
    st = turn.state(session_id)
    assert st["pending"] and st["pending"]["stage"] == "readback", st["pending"]
    return st


@pytest.mark.slow
def test_an_interrupted_read_back_is_not_a_confirmation(live_call):
    """The hole this closes: the caller cuts off the read-back, so never
    hears the amount or the payee, and a bare yes a moment later would have
    executed the transfer anyway."""
    conn, call_id, session_id = live_call
    _reach_readback(conn, session_id)

    out = callsm.interrupt(conn, call_id, source="barge_in")
    assert out["pending_dropped"] == ["readback"]
    assert turn.state(session_id)["pending"] is None

    # A yes now confirms nothing, because there is nothing pending to confirm.
    before = _debited_balance(conn)
    t = turn.run_turn(conn, session_id, confirm=True)
    assert _debited_balance(conn) == before, \
        "an interrupted read-back must move no money"
    assert t.action_taken != "fund_transfer"


@pytest.mark.slow
def test_a_confirmed_read_back_still_executes(live_call):
    """The mirror of the test above. Interruption must not have broken the
    ordinary path."""
    conn, _, session_id = live_call
    _reach_readback(conn, session_id)
    t = turn.run_turn(conn, session_id, confirm=True)
    assert t.decision == "automated"
    assert t.auth.readback_confirmed is True


@pytest.mark.slow
def test_an_action_that_committed_before_the_interruption_stands(live_call):
    """Commit happens before the reply is spoken, so interrupting the reply
    cannot undo it. The money moved; the caller simply did not hear us say
    so."""
    conn, call_id, session_id = live_call
    _reach_readback(conn, session_id)
    before = _debited_balance(conn)
    t = turn.run_turn(conn, session_id, confirm=True)
    assert t.decision == "automated"
    committed = _debited_balance(conn)
    assert committed == before - 5000.0, "the transfer should have committed"

    callsm.interrupt(conn, call_id, played_ms=90.0, played_chars=3,
                     reply_chars=len(t.reply_text or ""), source="barge_in")
    assert _debited_balance(conn) == committed, \
        "interrupting the reply must not undo a committed transfer"


@pytest.mark.slow
def test_a_refused_action_after_a_passed_read_back_is_not_automated(live_call):
    """Passing all three checks means the caller was allowed to ask, not that
    the action happened. Recording an unregistered payee as `automated` told
    the dashboard an action was taken when it was refused."""
    conn, _, session_id = live_call
    from app.config import OTP_DEMO_CODE
    v = turn.record_verification(conn, session_id, None, source="demo_clip")
    assert v["passed"]
    turn.run_turn(conn, session_id, text="transfer 5000 rupees to Nobody")
    turn.run_turn(conn, session_id, otp=OTP_DEMO_CODE)
    if turn.state(session_id).get("pending", {}) is None:
        pytest.skip("that phrasing did not reach a read-back")
    t = turn.run_turn(conn, session_id, confirm=True)
    assert t.action_taken == "refuse"
    assert t.decision == "refused", "a refused action must not read as automated"
    assert "refused" in (t.decision_reason or "")
