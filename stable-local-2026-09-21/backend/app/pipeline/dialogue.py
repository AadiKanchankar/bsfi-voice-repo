"""A2 and A5. Confidence fusion, risk scoring, tier assignment, and the policy
that turns all of it into one of three outcomes: automated, refused, escalated.

Every number this module uses comes from config.py and every number it produces
lands in the trace. The test in tests/test_risk.py recomputes the risk score
from trace.risk_components alone and asserts it matches trace.risk_score, which
is the machine-checked version of the claim the paper makes.

Two safety properties are enforced here rather than hoped for:

  hard override   fraud_report, dispute_txn and agent_request are tier 3
                  regardless of the score. A bug in the arithmetic must never
                  be able to automate a fraud report.
  tier ratchet    within a session the tier never decreases. An attacker cannot
                  lower their own risk by asking an innocent question after a
                  refused transfer.
"""
from __future__ import annotations

import math
from typing import Iterable

from ..config import (AMOUNT_MAX, FUSION_ALPHA, FUSION_BETA, FUSION_GAMMA,
                      GROUNDED_INTENTS, HARD_TIER3_INTENTS, HISTORY_LAMBDA,
                      RETRIEVAL_INTENTS,
                      INTENT_SENSITIVITY, MIN_TIER_BY_INTENT, PUBLIC_INTENTS,
                      RATCHET_EXEMPT_INTENTS, RATCHET_MIN_INTENT_CONFIDENCE,
                      RISK_WEIGHTS, TIER_CUTPOINTS, TIER_REQUIRING_OTP,
                      TIER_REQUIRING_VERIFICATION, TIER_TAU)


# ---------------------------------------------------------------- A2

def fuse_confidence(c_asr: float, c_intent: float, c_retr: float | None) -> dict:
    """c_final = c_asr^alpha * c_intent^beta * c_retr^gamma.

    Geometric, not arithmetic, so one weak signal can veto automation on its
    own. An average lets a confident intent hide a terrible transcript, and a
    terrible transcript is exactly the failure this system has to catch.
    """
    cr = 1.0 if c_retr is None else max(c_retr, 1e-6)
    ca, ci = max(c_asr, 1e-6), max(c_intent, 1e-6)
    c_final = (ca ** FUSION_ALPHA) * (ci ** FUSION_BETA) * (cr ** FUSION_GAMMA)
    return {"c_asr": round(ca, 4), "c_intent": round(ci, 4), "c_retr": round(cr, 4),
            "alpha": FUSION_ALPHA, "beta": FUSION_BETA, "gamma": FUSION_GAMMA,
            "c_final": round(float(c_final), 4)}


# ---------------------------------------------------------------- A5 terms

def sens(intent: str | None) -> float:
    return INTENT_SENSITIVITY.get(intent or "out_of_scope", 0.5)


def norm_amount(amount: float | None) -> float:
    """min(1, log1p(a) / log1p(A_max)). Log scale because the step from 1,000
    to 10,000 rupees matters more than the step from 190,000 to 200,000."""
    if not amount or amount <= 0:
        return 0.0
    return min(1.0, math.log1p(amount) / math.log1p(AMOUNT_MAX))


def dev_history(anomalies: Iterable[str] | int) -> float:
    """1 - exp(-lam * n). Saturating, so a session with six anomalies is not
    treated as six times worse than a session with one."""
    n = anomalies if isinstance(anomalies, int) else len(list(anomalies))
    return 1.0 - math.exp(-HISTORY_LAMBDA * n)


def requires_identity(intent: str | None) -> bool:
    """Whether knowing who is speaking matters for this intent.

    Public information does not need an identity, so an unverified caller
    carries no verification deficit when asking for it. Scoring those turns
    with s_verify = 0 would add a flat 0.25 to every one of them, putting them
    at or above t1 and making tier 0 unreachable. See ALGORITHMS.md A5.
    """
    return (intent or "out_of_scope") not in PUBLIC_INTENTS


def risk_score(intent: str | None, amount: float | None, s_verify: float | None,
               anomalies: Iterable[str] | int) -> tuple[float, dict]:
    """R = w1*sens + w2*norm(amount) + w3*(1 - s_verify) + w4*dev(history).

    Returns (R, components). The components dict carries every raw term, its
    weight and its weighted contribution, because the dashboard renders it and
    because a reviewer must be able to add the column up by hand.
    """
    anomaly_list = [] if isinstance(anomalies, int) else list(anomalies)
    n_anom = anomalies if isinstance(anomalies, int) else len(anomaly_list)
    identity_needed = requires_identity(intent)
    raw = {
        "sens": sens(intent),
        "amount": norm_amount(amount),
        "verify": (1.0 - (s_verify if s_verify is not None else 0.0)) if identity_needed else 0.0,
        "history": dev_history(n_anom),
    }
    weighted = {k: RISK_WEIGHTS[k] * v for k, v in raw.items()}
    R = sum(weighted.values())
    # Stored at full precision on purpose. A reviewer must be able to
    # recompute R from these numbers and land on the stored value exactly;
    # rounding for display is the dashboard's job, not the record's.
    components = {
        "raw": dict(raw),
        "weights": dict(RISK_WEIGHTS),
        "weighted": dict(weighted),
        "inputs": {"intent": intent, "amount": amount, "s_verify": s_verify,
                   "anomalies": anomaly_list, "n_anomalies": n_anom,
                   "identity_required": identity_needed},
        "constants": {"A_max": AMOUNT_MAX, "lambda": HISTORY_LAMBDA},
        "R": float(R),
    }
    return float(R), components


def recompute_from_components(components: dict) -> float:
    """Independent recomputation used by the property test. Reads only what the
    trace stored, never the live inputs."""
    return float(sum(components["weights"][k] * components["raw"][k]
                     for k in components["weights"]))


def tier_from_score(R: float) -> int:
    t1, t2, t3 = TIER_CUTPOINTS
    if R < t1:
        return 0
    if R < t2:
        return 1
    if R < t3:
        return 2
    return 3


def ratchet_applies(intent: str | None) -> bool:
    """Whether the session floor binds this turn.

    Public-information intents are exempt. They touch no account and reveal
    nothing identity-bound, so answering one at tier 0 after an earlier
    escalation leaks nothing. Without this exemption a single misheard turn
    makes the assistant refuse to quote its own published interest rates for
    the rest of the call, which is what testing actually showed.
    """
    return (intent or "out_of_scope") not in RATCHET_EXEMPT_INTENTS


def ratchet_should_raise(intent: str | None, intent_confidence: float | None,
                         new_tier: int, session_floor: int) -> bool:
    """Whether THIS turn is allowed to raise the session floor.

    A turn escalates on suspicion, which is right. It should only pin the rest
    of the session when the system was confident about what it heard, because
    the alternative is that one garbled transcript ends the call.
    """
    if new_tier <= session_floor:
        return False
    return (intent_confidence or 0.0) >= RATCHET_MIN_INTENT_CONFIDENCE


def assign_tier(R: float, intent: str | None, session_floor: int = 0) -> dict:
    """Tier is the maximum of three things: what the score says, what the
    intent's own floor demands, and where this session has already been.

    The score can only push a turn up. It can never talk a card block down to
    a tier that skips the read-back, and it can never talk a fraud report down
    at all. The session floor is skipped for public-information intents; see
    ratchet_applies.
    """
    scored = tier_from_score(R)
    overridden = (intent or "") in HARD_TIER3_INTENTS
    intent_floor = 3 if overridden else MIN_TIER_BY_INTENT.get(intent or "", 0)
    applies = ratchet_applies(intent)
    effective_floor = session_floor if applies else 0
    tier = max(scored, intent_floor, effective_floor)
    return {"tier": tier, "scored_tier": scored, "overridden": overridden,
            "intent_floor": intent_floor, "floored": intent_floor > scored,
            "ratcheted": effective_floor > max(scored, intent_floor),
            "ratchet_applies": applies,
            "ratchet_exempt_reason": (None if applies else
                                      "public information, no identity required"),
            "session_floor": session_floor,
            "effective_floor": effective_floor,
            "cutpoints": list(TIER_CUTPOINTS)}


def tau_for(tier: int) -> float:
    return TIER_TAU[min(tier, len(TIER_TAU) - 1)]


def ceiling_for(tier: int) -> float:
    """The R below which a turn at this tier may be automated. Tier 3 has none."""
    return TIER_CUTPOINTS[tier] if tier < len(TIER_CUTPOINTS) else 0.0


# ---------------------------------------------------------------- the gate

def gate(*, tier: int, R: float, c_final: float, needs_grounding: bool,
         grounded: bool, verification_passed: bool | None,
         otp_passed: bool | None, readback_confirmed: bool | None) -> dict:
    """Automate only when every condition holds. Otherwise refuse or escalate.

    The order of the checks is the order of the explanation the dashboard
    shows, so the first failing condition is the decision reason.
    """
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    tau = tau_for(tier)
    ceiling = ceiling_for(tier)

    if tier >= 3:
        add("tier", False, "tier 3 requires a human agent, automation is not available")
        return {"automate": False, "outcome": "escalated", "checks": checks,
                "tau": tau, "ceiling": ceiling,
                "reason": "tier 3: mandatory human handover"}

    add("risk_ceiling", R < ceiling, f"R = {R:.4f} must be below {ceiling:.2f} for tier {tier}")
    add("confidence", c_final >= tau, f"c_final = {c_final:.4f} must reach tau = {tau:.2f}")
    if needs_grounding:
        add("grounding", grounded, "intent requires a policy passage above the similarity floor")
    if tier >= TIER_REQUIRING_VERIFICATION:
        add("speaker_verification", bool(verification_passed),
            "tier requires passive speaker verification")
    if tier >= TIER_REQUIRING_OTP:
        add("otp", bool(otp_passed), "tier requires a one time password")
        add("readback", bool(readback_confirmed), "tier requires a spoken read-back confirmation")

    failed = [c for c in checks if not c["passed"]]
    if not failed:
        return {"automate": True, "outcome": "automated", "checks": checks,
                "tau": tau, "ceiling": ceiling, "reason": "all conditions met"}

    first = failed[0]
    # A failure to ground is a refusal. Everything else escalates to a human,
    # because the customer still has a problem that somebody has to solve.
    outcome = "refused" if first["check"] == "grounding" else "escalated"
    if first["check"] == "confidence" and tier == 0:
        outcome = "refused"
    return {"automate": False, "outcome": outcome, "checks": checks,
            "tau": tau, "ceiling": ceiling,
            "reason": f"{first['check']} failed: {first['detail']}"}


def runs_retrieval(intent: str | None) -> bool:
    """Whether to search the policy knowledge base for this intent."""
    return (intent or "out_of_scope") in RETRIEVAL_INTENTS


def needs_grounding(intent: str | None) -> bool:
    """Whether an empty retrieval result must block the answer.

    Stricter than runs_retrieval. An intent is grounded when the policy
    knowledge base is the only authoritative source for it, so nothing above
    the floor means there is no answer to give and the turn must refuse.
    out_of_scope is grounded by definition: it is the class that exists to be
    refused.
    """
    return (intent or "out_of_scope") in GROUNDED_INTENTS or intent == "out_of_scope"
