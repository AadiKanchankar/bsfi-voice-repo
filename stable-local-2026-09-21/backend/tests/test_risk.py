"""A2 and A5. Deterministic, so exact values, plus the property test the paper
leans on: the risk score must be recomputable from the trace alone.
"""
import math
import random

import pytest

from app.config import (AMOUNT_MAX, HISTORY_LAMBDA, RISK_WEIGHTS, TIER_CUTPOINTS,
                        TIER_TAU)
from app.pipeline import dialogue


def test_weights_sum_to_one():
    assert abs(sum(RISK_WEIGHTS.values()) - 1.0) < 1e-12


def test_norm_amount_is_log_scaled():
    assert dialogue.norm_amount(None) == 0.0
    assert dialogue.norm_amount(0) == 0.0
    assert dialogue.norm_amount(AMOUNT_MAX) == pytest.approx(1.0)
    assert dialogue.norm_amount(10 * AMOUNT_MAX) == 1.0          # clamped
    # The jump from 1k to 10k must be larger than 190k to 200k. That is the
    # entire reason for the log scale.
    assert (dialogue.norm_amount(10_000) - dialogue.norm_amount(1_000)) > \
           (dialogue.norm_amount(200_000) - dialogue.norm_amount(190_000))


def test_dev_history_saturates():
    assert dialogue.dev_history(0) == 0.0
    assert dialogue.dev_history(1) == pytest.approx(1 - math.exp(-HISTORY_LAMBDA))
    assert dialogue.dev_history(100) == pytest.approx(1.0, abs=1e-6)
    assert dialogue.dev_history(["new_device", "unusual_hour"]) == \
           pytest.approx(1 - math.exp(-2 * HISTORY_LAMBDA))


def test_risk_score_exact_value():
    R, c = dialogue.risk_score("block_card", None, 0.8, 0)
    # 0.40*0.70 + 0.25*0 + 0.25*(1-0.8) + 0.10*0
    assert R == pytest.approx(0.40 * 0.70 + 0.25 * 0.20)
    assert c["raw"]["sens"] == 0.70
    assert c["raw"]["verify"] == pytest.approx(0.2)


def test_missing_verification_raises_risk():
    with_verify, _ = dialogue.risk_score("get_balance", None, 0.9, 0)
    without, _ = dialogue.risk_score("get_balance", None, None, 0)
    assert without > with_verify


def test_tier_boundaries():
    t1, t2, t3 = TIER_CUTPOINTS
    assert dialogue.tier_from_score(0.0) == 0
    assert dialogue.tier_from_score(t1 - 1e-9) == 0
    assert dialogue.tier_from_score(t1) == 1
    assert dialogue.tier_from_score(t2) == 2
    assert dialogue.tier_from_score(t3) == 3
    assert dialogue.tier_from_score(1.0) == 3


@pytest.mark.parametrize("intent", ["fraud_report", "dispute_txn", "agent_request"])
def test_hard_override_beats_any_score(intent):
    """A scoring bug must never be able to automate a fraud report."""
    out = dialogue.assign_tier(0.0, intent, session_floor=0)
    assert out["tier"] == 3 and out["overridden"] is True


def test_session_ratchet_holds_for_account_access():
    out = dialogue.assign_tier(0.01, "get_balance", session_floor=2)
    assert out["tier"] == 2 and out["ratcheted"] is True
    assert out["scored_tier"] == 0


def test_ratchet_does_not_gag_public_information():
    """One misheard turn used to make the assistant refuse to quote its own
    published interest rates for the rest of the call."""
    out = dialogue.assign_tier(0.01, "product_info", session_floor=3)
    assert out["tier"] == 0
    assert out["ratchet_applies"] is False
    assert out["ratchet_exempt_reason"]


@pytest.mark.parametrize("intent", ["product_info", "branch_ifsc", "out_of_scope"])
def test_public_intents_are_ratchet_exempt(intent):
    assert dialogue.ratchet_applies(intent) is False


@pytest.mark.parametrize("intent", ["get_balance", "block_card", "fund_transfer"])
def test_account_intents_are_not_ratchet_exempt(intent):
    assert dialogue.ratchet_applies(intent) is True


def test_a_low_confidence_escalation_does_not_pin_the_session():
    """A garbled transcript should escalate the turn and leave the call usable."""
    assert dialogue.ratchet_should_raise("dispute_txn", 0.16, 3, 0) is False
    assert dialogue.ratchet_should_raise("dispute_txn", 0.90, 3, 0) is True
    assert dialogue.ratchet_should_raise("get_balance", 0.99, 1, 2) is False  # not a raise


def test_tier3_tau_is_unreachable():
    assert TIER_TAU[3] > 1.0
    verdict = dialogue.gate(tier=3, R=0.1, c_final=1.0, needs_grounding=False,
                            grounded=True, verification_passed=True,
                            otp_passed=True, readback_confirmed=True)
    assert verdict["automate"] is False and verdict["outcome"] == "escalated"


def test_fusion_is_geometric_and_vetoable():
    """An average would let a confident intent hide a terrible transcript."""
    good = dialogue.fuse_confidence(0.95, 0.95, 0.95)["c_final"]
    bad_asr = dialogue.fuse_confidence(0.05, 0.99, 0.99)["c_final"]
    assert good > 0.9
    assert bad_asr < 0.5, bad_asr
    arithmetic = 0.3 * 0.05 + 0.45 * 0.99 + 0.25 * 0.99
    assert bad_asr < arithmetic, "geometric fusion must punish harder than an average"


def test_fusion_exponents_sum_to_one():
    out = dialogue.fuse_confidence(0.5, 0.5, 0.5)
    assert abs(out["alpha"] + out["beta"] + out["gamma"] - 1.0) < 1e-12
    assert out["c_final"] == pytest.approx(0.5)


def test_gate_reports_the_first_failing_condition():
    verdict = dialogue.gate(tier=1, R=0.3, c_final=0.1, needs_grounding=False,
                            grounded=True, verification_passed=True,
                            otp_passed=True, readback_confirmed=True)
    assert verdict["automate"] is False
    assert "confidence" in verdict["reason"]


def test_gate_refuses_when_ungrounded():
    verdict = dialogue.gate(tier=0, R=0.05, c_final=0.9, needs_grounding=True,
                            grounded=False, verification_passed=None,
                            otp_passed=True, readback_confirmed=True)
    assert verdict["outcome"] == "refused"


def test_recompute_from_components_matches_stored_score():
    """The property the paper claims: a reviewer can recompute the decision
    from the trace alone, with no access to the process that produced it."""
    rng = random.Random(7)
    intents = list(dialogue.INTENT_SENSITIVITY)
    for _ in range(500):
        intent = rng.choice(intents)
        amount = rng.choice([None, 0, 500, 12_000, 199_999, 5_000_000])
        s_verify = rng.choice([None, 0.0, 0.31, 0.77, 1.0])
        anomalies = rng.sample(["new_device", "unusual_hour", "first_ever_payee",
                                "rapid_repeat_attempts"], rng.randint(0, 4))
        R, components = dialogue.risk_score(intent, amount, s_verify, anomalies)
        assert dialogue.recompute_from_components(components) == pytest.approx(R, abs=1e-9)
        assert components["R"] == R


# ---------------------------------------------------------------- tier floors

def test_public_information_can_reach_tier_zero():
    """Without the public-intent rule every unverified turn scores at least
    0.25 = t1 and tier 0 is unreachable, which contradicts its own definition."""
    R, c = dialogue.risk_score("product_info", None, None, 0)
    assert c["raw"]["verify"] == 0.0
    assert c["inputs"]["identity_required"] is False
    assert dialogue.assign_tier(R, "product_info")["tier"] == 0


def test_account_intents_still_pay_the_verification_term():
    R, c = dialogue.risk_score("get_balance", None, None, 0)
    assert c["raw"]["verify"] == 1.0
    assert c["inputs"]["identity_required"] is True
    assert dialogue.assign_tier(R, "get_balance")["tier"] >= 1


@pytest.mark.parametrize("intent,floor", [
    ("get_balance", 1), ("mini_statement", 1),
    ("block_card", 2), ("fund_transfer", 2), ("limit_change", 2), ("add_payee", 2),
    ("fraud_report", 3), ("dispute_txn", 3), ("agent_request", 3),
])
def test_intent_floor_holds_even_with_perfect_verification(intent, floor):
    """A confident identity must not be able to skip the read-back on an
    action that mutates account state."""
    R, _ = dialogue.risk_score(intent, None, 1.0, 0)
    out = dialogue.assign_tier(R, intent)
    assert out["tier"] >= floor, (intent, R, out)


def test_score_can_still_raise_a_turn_above_its_floor():
    low, _ = dialogue.risk_score("get_balance", None, 1.0, 0)
    high, _ = dialogue.risk_score("get_balance", 150_000, None, 4)
    assert dialogue.assign_tier(high, "get_balance")["tier"] > \
           dialogue.assign_tier(low, "get_balance")["tier"]


def test_retrieval_and_grounding_are_different_questions():
    """A cheque status comes from the cheque table, so an empty policy search
    must not block it. Conflating the two made the assistant refuse questions
    it could answer from the core banking data."""
    assert dialogue.runs_retrieval("cheque_status") is True
    assert dialogue.needs_grounding("cheque_status") is False
    assert dialogue.runs_retrieval("branch_ifsc") is True
    assert dialogue.needs_grounding("branch_ifsc") is False
    assert dialogue.needs_grounding("product_info") is True
    assert dialogue.needs_grounding("apply_loan") is True
    assert dialogue.needs_grounding("out_of_scope") is True
    assert dialogue.runs_retrieval("get_balance") is False
    assert dialogue.needs_grounding("get_balance") is False
