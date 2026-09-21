"""Contextual Language Understanding.

What it is for: real speech is code-mixed, elliptical and compound. "Mera
balance batao aur last transaction bhi" is one utterance with two requests in
two languages, and "aur uske pehle wali?" only means anything given the turn
before it. A single-label classifier over a fixed utterance bank cannot
represent either, which is the limitation the frozen snapshot documents at
0.74 dominant-language accuracy.

What it is NOT for, and this is the part that matters for a banking system:
the CLU never decides anything. It reads an utterance and returns structured
meaning. Risk scoring, authentication, retrieval grounding, the tier ladder
and the automation gate are unchanged and remain authoritative. The
deterministic classifier keeps running on every turn regardless, and:

  * a turn only reaches the model when the deterministic layer is unsure,
    the utterance is code-mixed, or it looks like a follow-up
  * the model's output is schema-validated, and anything malformed, unknown
    or out of range is discarded in favour of the deterministic result
  * the model may RAISE the assessed risk of a turn and never lower it

That last rule is what makes this safe to try. A model that misreads a fraud
report as a product question cannot downgrade the turn, because the
deterministic reading is kept whenever it is the more serious of the two.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from ..config import (CLU_BASELINE_TRUSTED_ABOVE, CLU_CALL_BELOW_CONFIDENCE,
                      CLU_CALL_BELOW_MARGIN, CLU_CALL_ON_CODE_MIX,
                      CLU_CALL_ON_COMPOUND, CLU_CALL_ON_FOLLOWUP,
                      CLU_COMPOUND_MIN_WORDS, CLU_CONTEXT_TURNS,
                      CLU_MAY_LOWER_RISK, CLU_OVERRIDE_NEEDS_CONFIDENCE,
                      CLU_PROVIDER, HARD_TIER3_INTENTS, INTENT_SENSITIVITY)
from .prompt import PROMPT_VERSION
from .providers import ProviderReply, get_provider
from .schema import CLUResult

__all__ = ["understand_turn", "should_call", "CLUOutcome", "CLUResult",
           "merge_with_baseline", "enabled"]

# Coordinators. A turn joining two asks needs the model even when the head is
# confident, because a single-label classifier cannot represent the second
# one at any confidence.
_COORDINATOR = re.compile(
    r"\b(and also|and then|as well as|along with|and|aur|और|ani|आणि|pan|पण|"
    r"bhi|भी|plus|also|then)\b", re.I)


def _coordinates_two_asks(text: str) -> bool:
    """A coordinator with real content on both sides.

    Bare "and" is too common to trigger on by itself: "terms and conditions"
    is one ask. Requiring a few words either side of the join is a cheap
    stand-in for two clauses, and it is a router heuristic, so a miss costs a
    model call not a wrong answer.
    """
    words = (text or "").split()
    if len(words) < CLU_COMPOUND_MIN_WORDS:
        return False
    for i, w in enumerate(words):
        if _COORDINATOR.fullmatch(w.strip(".,!?;:")) and i >= 3 and len(words) - i - 1 >= 3:
            return True
    return False

# Words that make a turn look like it refers to something already said.
_FOLLOWUP = re.compile(
    r"\b(aur|और|and|uske|उसके|usse|that|those|it|iske|इसके|pehle|पहले|before|"
    r"next|agla|अगला|wali|वाली|wala|वाला|tyachya|त्याच्या|te|ते|same|phir|फिर)\b",
    re.I)


@dataclass
class CLUOutcome:
    """Everything the trace needs to explain what the language layer did."""
    called: bool
    reason: str
    result: CLUResult | None = None
    provider: str = "null"
    model: str = "none"
    latency_ms: float = 0.0
    leaves_machine: bool = False
    prompt_version: str = PROMPT_VERSION
    error: str | None = None
    raw_rejected: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    meta: dict = field(default_factory=dict)

    def to_trace(self) -> dict:
        out = {
            "called": self.called, "reason": self.reason, "provider": self.provider,
            "model": self.model, "latency_ms": round(self.latency_ms, 1),
            "prompt_version": self.prompt_version,
            "data_left_the_machine": self.leaves_machine,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }
        if self.result:
            out["result"] = self.result.model_dump()
        if self.error:
            out["error"] = self.error
        if self.raw_rejected:
            # Truncated: enough to debug a bad model, not a transcript store.
            out["rejected_output"] = self.raw_rejected[:300]
        return out | self.meta


def enabled() -> bool:
    return (CLU_PROVIDER or "null").lower() != "null"


def should_call(baseline_confidence: float, baseline_margin: float,
                code_mix_index: float, transcript: str,
                has_context: bool) -> tuple[bool, str]:
    """Whether this turn is worth a model call.

    Most turns are not. A confident, monolingual, single-intent request is
    something the logistic head already gets right, and routing it through a
    model buys nothing and costs latency.
    """
    if not enabled():
        return False, "CLU disabled"
    if baseline_confidence < CLU_CALL_BELOW_CONFIDENCE:
        return True, (f"baseline intent confidence {baseline_confidence:.2f} is below "
                      f"{CLU_CALL_BELOW_CONFIDENCE}")
    if baseline_margin < CLU_CALL_BELOW_MARGIN:
        return True, (f"top two intents are {baseline_margin:.2f} apart, under "
                      f"{CLU_CALL_BELOW_MARGIN}")
    if CLU_CALL_ON_CODE_MIX and code_mix_index > 0:
        return True, f"utterance is code-mixed, CMI {code_mix_index}"
    if CLU_CALL_ON_FOLLOWUP and has_context and _FOLLOWUP.search(transcript or ""):
        short = len((transcript or "").split()) <= 8
        if short:
            return True, "short utterance referring to something already said"
    if CLU_CALL_ON_COMPOUND and _coordinates_two_asks(transcript):
        return True, "utterance coordinates more than one request"
    return False, (f"baseline is confident ({baseline_confidence:.2f}) and the utterance "
                   f"is single-language and self-contained")


def _extract_json(text: str) -> dict | None:
    """Models fence their JSON, prefix it, or append an apology. Take the
    first balanced object and ignore the rest."""
    if not text:
        return None
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.I | re.M)
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


def understand_turn(transcript: str, context: list[dict] | None = None,
                    baseline_confidence: float = 1.0, baseline_margin: float = 1.0,
                    code_mix_index: float = 0.0,
                    provider_name: str | None = None) -> CLUOutcome:
    """The one entry point. Everything above this is provider-agnostic.

    Never raises. A provider that is down, slow, unauthenticated or talking
    nonsense produces a CLUOutcome with `result=None`, and the caller carries
    on with the deterministic reading.
    """
    context = (context or [])[-CLU_CONTEXT_TURNS:]
    call, reason = should_call(baseline_confidence, baseline_margin, code_mix_index,
                               transcript, bool(context))
    if not call:
        return CLUOutcome(called=False, reason=reason, provider=CLU_PROVIDER)

    provider = get_provider(provider_name)
    if not provider.available():
        return CLUOutcome(called=False, reason=f"{provider.name} provider is not available",
                          provider=provider.name, leaves_machine=provider.leaves_machine,
                          error="provider unavailable")

    t0 = time.perf_counter()
    try:
        reply: ProviderReply = provider.complete(transcript, context)
    except Exception as exc:                                # noqa: BLE001
        return CLUOutcome(called=True, reason=reason, provider=provider.name,
                          leaves_machine=provider.leaves_machine,
                          latency_ms=(time.perf_counter() - t0) * 1000,
                          error=f"{type(exc).__name__}: {exc}")

    base = CLUOutcome(called=True, reason=reason, provider=reply.provider,
                      model=reply.model, latency_ms=reply.latency_ms,
                      leaves_machine=reply.leaves_machine,
                      prompt_tokens=reply.prompt_tokens,
                      completion_tokens=reply.completion_tokens,
                      meta=reply.meta)
    if reply.error:
        base.error = reply.error
        return base

    payload = _extract_json(reply.text)
    if payload is None:
        base.error = "provider did not return a JSON object"
        base.raw_rejected = reply.text
        return base
    try:
        base.result = CLUResult.model_validate(payload)
    except Exception as exc:                                # noqa: BLE001
        base.error = f"schema rejected the output: {exc}"
        base.raw_rejected = reply.text
    return base


def merge_with_baseline(baseline_intent: str, baseline_confidence: float,
                        baseline_slots: dict, outcome: CLUOutcome) -> dict:
    """Combine the two readings under the safety floor.

    The rule: the CLU may raise the assessed risk of a turn, never lower it.
    Concretely, if either reading is a hard tier 3 intent, or the
    deterministic reading is more sensitive than the CLU's, the deterministic
    one is kept. Slots are merged with the deterministic rules winning on any
    key they extracted, because those rules are auditable and the model is
    not.
    """
    decision = {
        "intent": baseline_intent, "confidence": baseline_confidence,
        "slots": dict(baseline_slots), "source": "baseline",
        "sub_intents": [], "references": [], "normalized_text": None,
        "override_blocked": False, "override_reason": None,
        "hard_override_relaxed": None,
    }
    r = outcome.result
    if r is None:
        decision["override_reason"] = outcome.error or outcome.reason
        return decision

    base_sens = INTENT_SENSITIVITY.get(baseline_intent, 0.5)
    clu_sens = INTENT_SENSITIVITY.get(r.intent, 0.5)
    baseline_is_hard = baseline_intent in HARD_TIER3_INTENTS
    clu_is_hard = r.intent in HARD_TIER3_INTENTS

    # Sub-intents, references and the normalisation are additive: they cannot
    # reduce risk, so they are taken regardless of which intent wins.
    decision["sub_intents"] = list(r.sub_intents)
    decision["references"] = list(r.references)
    decision["normalized_text"] = r.normalized_text

    baseline_trusted = baseline_confidence >= CLU_BASELINE_TRUSTED_ABOVE
    clu_sure = r.confidence >= CLU_OVERRIDE_NEEDS_CONFIDENCE

    if not CLU_MAY_LOWER_RISK and baseline_is_hard and not clu_is_hard:
        # Downgrading a mandatory-handover intent is the most dangerous thing
        # this merge can do, so it takes both a weak deterministic reading and
        # a strong model one.
        if baseline_trusted or not clu_sure:
            decision["override_blocked"] = True
            decision["override_reason"] = (
                f"the deterministic classifier read this as {baseline_intent}, a "
                f"mandatory-handover intent, at {baseline_confidence:.2f} confidence. "
                f"A language model does not get to talk that down to {r.intent}.")
            return decision
        decision["hard_override_relaxed"] = (
            f"kept the language layer's {r.intent} ({r.confidence:.2f}) over a "
            f"{baseline_confidence:.2f}-confidence {baseline_intent} from the "
            f"deterministic head, which is below the {CLU_BASELINE_TRUSTED_ABOVE} "
            f"threshold at which that head counts as evidence")

    if not CLU_MAY_LOWER_RISK and clu_sens < base_sens and baseline_trusted:
        decision["override_blocked"] = True
        decision["override_reason"] = (
            f"{r.intent} is less sensitive than the deterministic reading "
            f"{baseline_intent} ({clu_sens} against {base_sens}) and that reading was "
            f"confident at {baseline_confidence:.2f}, so the safer one is kept.")
        return decision

    decision["intent"] = r.intent
    decision["confidence"] = r.confidence
    decision["source"] = "clu"
    # Deterministic slot rules win where they fired: they are readable in a
    # way model output is not.
    merged = {k: v for k, v in r.entities.items() if v not in (None, "")}
    merged.update(baseline_slots)
    decision["slots"] = merged
    return decision
