"""The investment boundary.

The assistant answers facts about products and about what a customer already
holds. It does not recommend. Under the SEBI (Investment Advisers)
Regulations 2013 that advice may only come from a registered adviser, and an
automated assistant is not one, so a request for it is a mandatory human
handover in the same class as a fraud report.

The tests that matter here are the ones asserting it will NOT answer.
"""
import pytest

from app.banking import actions
from app.banking.mock_core import MockCore
from app.config import (HARD_TIER3_INTENTS, INTENT_SENSITIVITY,
                        MIN_TIER_BY_INTENT, NON_RATCHETING_TIER3)
from app.pipeline import dialogue
from app.trace import ComplianceTrace


def blank_trace():
    return ComplianceTrace(session_id="00000000-0000-0000-0000-000000000001",
                           turn_index=0,
                           consent_ref="00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------- the boundary

def test_advice_is_a_mandatory_handover():
    assert "investment_advice" in HARD_TIER3_INTENTS
    assert MIN_TIER_BY_INTENT["investment_advice"] == 3
    assert INTENT_SENSITIVITY["investment_advice"] == 1.00


def test_advice_can_never_be_automated_whatever_the_score():
    out = dialogue.assign_tier(0.0, "investment_advice", session_floor=0)
    assert out["tier"] == 3 and out["overridden"] is True
    verdict = dialogue.gate(tier=3, R=0.0, c_final=1.0, needs_grounding=False,
                            grounded=True, verification_passed=True,
                            otp_passed=True, readback_confirmed=True)
    assert verdict["automate"] is False and verdict["outcome"] == "escalated"


def test_the_refusal_names_the_reason_rather_than_transferring_silently():
    out = actions.investment_advice(blank_trace())
    assert out["action_taken"] == "escalate_to_investment_adviser"
    assert out["result"]["automated_answer_given"] is False
    assert "SEBI" in out["result"]["regulation"]
    for lang in ("en", "hi", "mr"):
        assert out["reply"][lang].strip()
    reply = out["reply"]["en"].lower()
    assert "registered investment adviser" in reply
    assert "not" in reply


def test_the_refusal_does_not_sneak_in_a_hedged_recommendation():
    """A hedged recommendation is still a recommendation."""
    reply = actions.investment_advice(blank_trace())["reply"]["en"].lower()
    for weasel in ("i would suggest", "you should consider", "a good option",
                   "i recommend", "better returns", "you could invest"):
        assert weasel not in reply, f"the refusal contains {weasel!r}"


def test_asking_for_advice_does_not_lock_the_rest_of_the_call():
    """Wanting advice says nothing about risk. Ratcheting the session on it
    would lock a customer out of their own balance for asking about stocks."""
    assert "investment_advice" in NON_RATCHETING_TIER3
    assert "agent_request" in NON_RATCHETING_TIER3
    # But a fraud report still elevates the call.
    assert "fraud_report" not in NON_RATCHETING_TIER3
    assert "dispute_txn" not in NON_RATCHETING_TIER3


def test_info_is_account_data_and_needs_verification():
    assert MIN_TIER_BY_INTENT["investment_info"] >= 1
    assert "investment_info" not in HARD_TIER3_INTENTS


# ---------------------------------------------------------------- facts

@pytest.fixture()
def core(conn):
    conn.execute("INSERT INTO holdings (holding_id, customer_id, kind, name, units,"
                 " avg_cost, last_price, as_of) VALUES"
                 " ('H1','C1','equity','Demo Infotech Ltd',120,1280.0,1465.30,'2026-09-20')")
    conn.execute("INSERT INTO holdings (holding_id, customer_id, kind, name, units,"
                 " avg_cost, last_price, as_of) VALUES"
                 " ('H2','C1','mutual_fund','Demo Bluechip Growth Fund',1000,54.2,68.95,'2026-09-20')")
    conn.execute("INSERT INTO sips (sip_id, customer_id, fund, amount, day_of_month,"
                 " started_on) VALUES ('S1','C1','Demo Bluechip Growth Fund',5000,6,'2024-04-06')")
    conn.commit()
    return MockCore(conn)


def test_portfolio_value_is_arithmetic_not_opinion(core):
    p = core.portfolio_value("C1")
    assert p["n_holdings"] == 2
    assert p["value"] == pytest.approx(120 * 1465.30 + 1000 * 68.95, abs=0.01)
    assert p["cost"] == pytest.approx(120 * 1280.0 + 1000 * 54.2, abs=0.01)
    assert p["unrealised"] == pytest.approx(p["value"] - p["cost"], abs=0.01)


def test_a_named_holding_is_found_and_priced(core):
    out = actions.investment_info(core, "C1", blank_trace(), {}, "how many Infotech shares")
    assert out["action_taken"] == "investment_info_holding"
    assert out["result"]["holding"]["name"] == "Demo Infotech Ltd"
    assert "120" in out["reply"]["en"]


def test_portfolio_answer_carries_the_past_performance_warning(core):
    out = actions.investment_info(core, "C1", blank_trace(), {}, "what is my portfolio worth")
    assert out["action_taken"] == "investment_info_portfolio"
    assert "past performance" in out["reply"]["en"].lower()
    assert out["result"]["sips"]


def test_a_holding_answer_says_it_is_not_advice(core):
    out = actions.investment_info(core, "C1", blank_trace(), {}, "Demo Infotech")
    assert "not a recommendation" in out["reply"]["en"].lower()


def test_no_holdings_is_reported_plainly(core):
    out = actions.investment_info(core, "C-nobody", blank_trace(), {}, "portfolio")
    assert out["action_taken"] == "investment_info_none"
    assert out["result"]["n_holdings"] == 0


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_investment_replies_exist_in_every_language(core, lang):
    for out in (actions.investment_advice(blank_trace()),
                actions.investment_info(core, "C1", blank_trace(), {}, "portfolio")):
        assert out["reply"][lang].strip()


def test_hindi_and_marathi_investment_replies_are_devanagari(core):
    import re
    deva = re.compile(r"[ऀ-ॿ]")
    for out in (actions.investment_advice(blank_trace()),
                actions.investment_info(core, "C1", blank_trace(), {}, "portfolio")):
        for lang in ("hi", "mr"):
            assert deva.search(out["reply"][lang]), out["reply"][lang][:60]
