"""R6. Clarifying instead of transferring, and what happens after a transfer.

Two halves. The gate learns a fourth answer, `clarify`, so that not
understanding someone stops being a reason to fetch a human. And an
escalated call stops being silence: a case reference, one safe protective
action, the questions the agent would ask anyway, and a way out if nobody is
free.
"""
import json

import pytest

from app import escalation as esc
from app import turn
from app.config import PROTECTIVE_ACTIONS, PROTECTIVE_ACTIONS_ENABLED
from app.pipeline.dialogue import gate


def _gate(**kw):
    base = dict(tier=1, R=0.3, c_final=0.33, needs_grounding=False, grounded=True,
                verification_passed=True, otp_passed=True, readback_confirmed=True)
    return gate(**{**base, **kw})


# ---------------------------------------------------------------- clarify

def test_low_confidence_asks_instead_of_transferring():
    """The whole point. Not knowing what someone asked is a reason to ask."""
    assert _gate()["outcome"] == "clarify"


def test_two_failed_clarifications_in_a_row_escalate():
    assert _gate(clarifications=1)["outcome"] == "clarify"
    assert _gate(clarifications=2)["outcome"] == "escalated"


def test_asking_for_a_person_is_honoured_immediately():
    """Clarifying at someone who just said "put me through" is the most
    irritating thing a helpline can do."""
    assert _gate(agent_requested=True)["outcome"] == "escalated"


@pytest.mark.parametrize("kw,expected", [
    ({"tier": 3}, "escalated"),                       # hard override
    ({"R": 0.99, "c_final": 0.99}, "escalated"),      # genuine risk
    ({"verification_passed": False, "tier": 1, "c_final": 0.99}, "escalated"),
    # High confidence so that grounding is the only failing check: with a
    # low one, both fail and confidence is checked first, which is correct.
    # Asking what someone meant before refusing them is the better order.
    ({"needs_grounding": True, "grounded": False, "c_final": 0.99}, "refused"),
])
def test_only_the_confidence_check_clarifies(kw, expected):
    """A risk ceiling breach, a failed verification and tier 3 are decisions
    about whether this may be automated at all. No amount of asking the
    caller changes any of them."""
    assert _gate(**kw)["outcome"] == expected


def test_the_clarifying_question_names_at_most_two_options():
    """A spoken menu of five is a phone tree, which is the thing this
    system exists not to be."""
    from app.banking import actions
    from app.trace import ComplianceTrace
    import uuid
    t = ComplianceTrace(session_id=uuid.uuid4(), turn_index=0,
                        consent_ref=uuid.uuid4())
    out = actions.clarify(t, ["get_balance", "mini_statement", "cheque_status"], 1)
    assert len(out["result"]["options"]) <= 2
    assert "balance" in out["reply"]["en"]


def test_an_unclear_and_ungrounded_turn_asks_before_refusing():
    """Both checks fail. Confidence is evaluated first on purpose: telling
    someone you cannot help is worse than asking what they meant, when you
    are not certain what they meant."""
    assert _gate(needs_grounding=True, grounded=False, c_final=0.33)["outcome"] \
        == "clarify"


def test_a_clarify_with_nothing_to_offer_admits_it():
    from app.banking import actions
    from app.trace import ComplianceTrace
    import uuid
    t = ComplianceTrace(session_id=uuid.uuid4(), turn_index=0,
                        consent_ref=uuid.uuid4())
    reply = actions.clarify(t, [], 1)["reply"]["en"].lower()
    assert "did not" in reply or "again" in reply


# ---------------------------------------------------------------- protective

def test_only_the_card_freeze_is_enabled():
    """Everything else on the list is written out with a reason, so that
    'why not this one' has an answer in the file."""
    assert PROTECTIVE_ACTIONS_ENABLED == {"freeze_card"}
    assert [a["name"] for a in esc.available_actions("fraud_report")] == ["freeze_card"]


def test_an_action_nobody_signed_off_is_refused(conn):
    with pytest.raises(esc.NotWhitelisted) as e:
        esc.perform_protective_action(conn, name="lower_daily_limit",
                                      customer_id="CUST1000", case_id=None,
                                      confirmed=True)
    assert "sign-off" in str(e.value)


def test_reversing_a_transaction_is_never_on_the_list():
    """It resolves the dispute, which is exactly what tier 3 forbids
    automating. Listed in config so nobody adds it later thinking it was
    merely overlooked."""
    spec = next(a for a in PROTECTIVE_ACTIONS if a["name"] == "reverse_transaction")
    assert spec["reasons"] == [] and spec["reversible"] is False
    assert "NEVER" in spec["note"]


def test_every_enabled_action_is_reversible():
    for a in PROTECTIVE_ACTIONS:
        if a["name"] in PROTECTIVE_ACTIONS_ENABLED:
            assert a["reversible"] is True, a["name"]


def test_nothing_happens_without_an_explicit_yes(conn):
    out = esc.perform_protective_action(conn, name="freeze_card",
                                        customer_id="CUST1000", case_id=None,
                                        confirmed=False)
    assert out["performed"] is False
    assert "did not confirm" in out["reason"]


@pytest.mark.slow
def test_a_confirmed_freeze_is_performed_and_ledgered(live):
    case = esc.open_case(live, call_id=None, customer_id="CUST1000",
                         reason="fraud_report")
    out = esc.perform_protective_action(live, name="freeze_card",
                                        customer_id="CUST1000",
                                        case_id=case["case_id"], confirmed=True)
    assert out["performed"] and out["reversible"] is True
    kinds = [r["kind"] for r in live.execute("SELECT kind FROM ledger"
                                             " ORDER BY idx DESC LIMIT 20")]
    assert "protective_action" in kinds
    # Put it back: this is the demo database.
    live.execute("UPDATE cards SET status='active' WHERE customer_id='CUST1000'")
    live.commit()


# ---------------------------------------------------------------- the case

def test_a_case_gets_a_reference_a_caller_can_write_down(conn):
    case = esc.open_case(conn, call_id=None, customer_id="CUST1000",
                         reason="fraud_report")
    spoken = esc.case_reference(case["case_id"])
    # Character by character, not read as a word.
    assert len(spoken.split()) >= 6, spoken
    assert case["case_id"].startswith("CASE")


def test_intake_asks_what_the_agent_would_have_asked(conn):
    qs = esc.intake_questions("fraud_report")
    ids = {q["id"] for q in qs}
    assert {"when_noticed", "amount", "card_present"} <= ids
    for q in qs:                       # every question in every language
        assert q["en"] and q["hi"] and q["mr"]


def test_intake_answers_stick_to_the_case(conn):
    case = esc.open_case(conn, call_id=None, customer_id="CUST1000",
                         reason="fraud_report")
    esc.record_intake(conn, case["case_id"], {"when_noticed": "this morning"})
    esc.record_intake(conn, case["case_id"], {"amount": "about 5000"})
    row = conn.execute("SELECT intake FROM cases WHERE case_id=?",
                       (case["case_id"],)).fetchone()
    stored = json.loads(row["intake"])
    assert stored == {"when_noticed": "this morning", "amount": "about 5000"}


def test_no_agent_available_logs_it_and_says_so(conn):
    case = esc.open_case(conn, call_id=None, customer_id="CUST1000",
                         reason="fraud_report")
    out = esc.offer_callback(conn, case["case_id"])
    assert out["status"] == "callback"
    assert out["sms"] == "SIMULATED"
    reply = out["reply"].lower()
    assert "call you back" in reply
    assert "nothing on your account has been changed" in reply


def test_hold_updates_say_something_true(conn):
    out = esc.hold_update(3)
    assert out["queue_position"] == 3
    assert out["estimated_wait_minutes"] > 0
    assert "callback" in out["reply"].lower()


# ---------------------------------------------------------------- agent side

def test_an_agent_takes_a_case_and_gets_what_is_already_known(conn):
    s = turn.create_session(conn, "CUST1000")
    case = esc.open_case(conn, call_id=s["call_id"], customer_id="CUST1000",
                         reason="fraud_report")
    esc.record_intake(conn, case["case_id"], {"when_noticed": "this morning"})

    packet = esc.accept_case(conn, case["case_id"], "AGENT1")
    assert packet["intake"]["when_noticed"] == "this morning"
    assert packet["case"]["status"] == "open"          # row as it was
    assert conn.execute("SELECT status, assigned_agent FROM cases WHERE case_id=?",
                        (case["case_id"],)).fetchone()["status"] == "assigned"


def test_closing_a_case_records_the_outcome(conn):
    case = esc.open_case(conn, call_id=None, customer_id="CUST1000",
                         reason="dispute_txn")
    esc.accept_case(conn, case["case_id"], "AGENT1")
    out = esc.close_case(conn, case["case_id"], "AGENT1", "refund approved")
    assert out["status"] == "closed" and out["outcome"] == "refund approved"
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger")]
    assert {"case_opened", "case_accepted", "case_closed"} <= set(kinds)


def test_the_whole_escalated_call_is_in_the_ledger(conn):
    """Every step an agent or the assistant took, in order, verifiable."""
    from app.security import ledger
    s = turn.create_session(conn, "CUST1000")
    case = esc.open_case(conn, call_id=s["call_id"], customer_id="CUST1000",
                         reason="fraud_report")
    esc.record_intake(conn, case["case_id"], {"amount": "5000"})
    esc.accept_case(conn, case["case_id"], "AGENT1")
    esc.agent_reply(conn, case["case_id"], "AGENT1", "I have your case open.")
    esc.close_case(conn, case["case_id"], "AGENT1", "card reissued")

    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger ORDER BY idx")]
    for expected in ("case_opened", "case_intake", "case_accepted",
                     "agent_reply", "case_closed"):
        assert expected in kinds, expected
    assert ledger.verify(conn)["ok"] is True


# ---------------------------------------------------------------- acceptance

@pytest.mark.slow
def test_a_fraud_report_runs_end_to_end(live):
    """R6's acceptance criterion, in one test.

    Escalation, a reference number spoken so it can be written down, a card
    freeze offered and confirmed, intake answered, an agent accepting in the
    console, the agent's reply spoken to the caller, the case closed, and
    every step in the ledger with the chain still valid.
    """
    from app.security import ledger
    from app.banking.mock_core import MockCore

    voice = "CUST1000_0.wav" if live.execute(
        "SELECT 1 FROM speakers WHERE customer_id='CUST1000'").fetchone() else None
    s = turn.create_session(live, "CUST1000", device_id="pytest-fraud",
                            voice_clip=voice)
    before_cards = {c["card_id"]: c["status"] for c in MockCore(live).get_cards("CUST1000")}

    try:
        # 1. The caller reports fraud. Tier 3, so a human must handle it.
        t = turn.run_turn(live, s["session_id"],
                          text="Someone has made a fraudulent transaction on my account")
        assert t.risk_tier == 3
        assert t.decision == "escalated"
        assert t.handover_packet_ref, "a real escalation creates a handover packet"

        # 2. A case, with a reference the caller can write down.
        case = esc.open_case(live, call_id=s["call_id"], customer_id="CUST1000",
                             reason="fraud_report", trace_id=str(t.trace_id))
        spoken = esc.case_reference(case["case_id"])
        assert len(spoken.split()) >= 6, spoken

        # 3. One protective action is offered, and only after an explicit yes.
        offered = esc.available_actions("fraud_report")
        assert [a["name"] for a in offered] == ["freeze_card"]
        assert esc.perform_protective_action(
            live, name="freeze_card", customer_id="CUST1000",
            case_id=case["case_id"], confirmed=False,
            call_id=s["call_id"])["performed"] is False
        frozen = esc.perform_protective_action(
            live, name="freeze_card", customer_id="CUST1000",
            case_id=case["case_id"], confirmed=True, call_id=s["call_id"])
        assert frozen["performed"] and frozen["reversible"]

        # 4. Intake while they wait, so the agent does not ask again.
        qs = esc.intake_questions("fraud_report")
        esc.record_intake(live, case["case_id"],
                          {q["id"]: "answered" for q in qs})

        # 5. An agent takes it and receives the context.
        packet = esc.accept_case(live, case["case_id"], "AGENT1")
        assert packet["intake"]["when_noticed"] == "answered"
        assert packet.get("traces"), "the agent sees the conversation"

        # 6. The agent speaks to the caller, and closes the case.
        esc.agent_reply(live, case["case_id"], "AGENT1",
                        "I have frozen the card and raised a dispute.")
        closed = esc.close_case(live, case["case_id"], "AGENT1", "card reissued")
        assert closed["status"] == "closed"

        # 7. Every step is in the ledger and the chain still verifies.
        kinds = [r["kind"] for r in live.execute(
            "SELECT kind FROM ledger ORDER BY idx DESC LIMIT 40")]
        for expected in ("case_opened", "protective_action", "case_intake",
                         "case_accepted", "agent_reply", "case_closed"):
            assert expected in kinds, expected
        assert ledger.verify(live)["ok"] is True
    finally:
        # This is the demo database: unfreeze what the test froze.
        for card_id, status in before_cards.items():
            live.execute("UPDATE cards SET status=? WHERE card_id=?",
                         (status, card_id))
        live.commit()
