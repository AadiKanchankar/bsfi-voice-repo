"""The contextual language layer.

Most of this file is about what the CLU is NOT allowed to do. The layer is
useful because it reads messy speech better than a logistic head; it is safe
because a language model cannot move the risk assessment downwards, cannot
reach an action, and cannot break the turn when it misbehaves. Those three
properties are what is tested here.
"""
import json

import pytest

from app import clu
from app.clu.providers import (MockProvider, NullProvider,
                               OpenAICompatibleProvider, get_provider,
                               provider_names)
from app.clu.schema import CLUResult
from app.config import HARD_TIER3_INTENTS, INTENTS


def outcome(intent: str, confidence: float = 0.9, **kw) -> clu.CLUOutcome:
    return clu.CLUOutcome(called=True, reason="test",
                          result=CLUResult(intent=intent, language="en",
                                           confidence=confidence, **kw))


# ---------------------------------------------------------------- schema

def test_unknown_intent_is_rejected():
    with pytest.raises(ValueError):
        CLUResult(intent="transfer_all_the_money", language="en", confidence=0.99)


def test_unknown_sub_intents_are_dropped_not_fatal():
    r = CLUResult(intent="get_balance", sub_intents=["mini_statement", "nonsense"],
                  language="en", confidence=0.9)
    assert r.sub_intents == ["mini_statement"]


def test_sub_intent_cannot_duplicate_the_primary():
    r = CLUResult(intent="get_balance", sub_intents=["get_balance"],
                  language="en", confidence=0.9)
    assert r.sub_intents == []


def test_confidence_is_clamped():
    assert CLUResult(intent="get_balance", language="en", confidence=7).confidence == 1.0
    assert CLUResult(intent="get_balance", language="en", confidence=-3).confidence == 0.0


def test_two_languages_implies_code_mixed():
    r = CLUResult(intent="get_balance", language="hi", languages=["hi", "en"],
                  confidence=0.9)
    assert r.code_mixed is True and r.language == "code_mixed"


def test_free_text_fields_are_bounded():
    r = CLUResult(intent="get_balance", language="en", confidence=0.5,
                  notes="x" * 5000, normalized_text="y" * 5000)
    assert len(r.notes) <= 400 and len(r.normalized_text) <= 400


# ---------------------------------------------------------------- safety floor

def test_clu_may_not_downgrade_a_confident_fraud_report():
    """The single most important test in this file."""
    d = clu.merge_with_baseline("fraud_report", 0.82, {}, outcome("product_info", 0.99))
    assert d["intent"] == "fraud_report"
    assert d["override_blocked"] is True
    assert "not allowed" in d["override_reason"] or "does not get to" in d["override_reason"]


@pytest.mark.parametrize("hard", sorted(HARD_TIER3_INTENTS))
def test_no_hard_handover_intent_can_be_talked_down_when_confident(hard):
    for benign in ("product_info", "get_balance", "mini_statement", "branch_ifsc"):
        d = clu.merge_with_baseline(hard, 0.75, {}, outcome(benign, 1.0))
        assert d["intent"] == hard, f"{hard} was downgraded to {benign}"
        assert d["override_blocked"] is True


def test_clu_may_always_raise_risk():
    d = clu.merge_with_baseline("get_balance", 0.95, {}, outcome("fraud_report", 0.71))
    assert d["intent"] == "fraud_report" and d["source"] == "clu"


def test_a_noise_level_baseline_can_be_overridden_by_a_sure_model():
    """The deterministic head fired fraud_report at 0.30 on the harmless
    follow-up "aur uske pehle wali?". A 0.30 posterior is not evidence."""
    d = clu.merge_with_baseline("fraud_report", 0.30, {}, outcome("mini_statement", 0.88))
    assert d["intent"] == "mini_statement"
    assert d["hard_override_relaxed"]


def test_but_an_unsure_model_still_cannot_override_it():
    d = clu.merge_with_baseline("fraud_report", 0.30, {}, outcome("mini_statement", 0.55))
    assert d["intent"] == "fraud_report" and d["override_blocked"] is True


def test_less_sensitive_intent_is_refused_when_the_baseline_was_confident():
    d = clu.merge_with_baseline("fund_transfer", 0.80, {}, outcome("product_info", 0.99))
    assert d["intent"] == "fund_transfer" and d["override_blocked"] is True


def test_deterministic_slots_win_over_model_entities():
    """Rule-based extraction is auditable; model output is not."""
    d = clu.merge_with_baseline(
        "fund_transfer", 0.4, {"amount": 50000.0},
        outcome("fund_transfer", 0.95, entities={"amount": 999999, "payee": "Rohan"}))
    assert d["slots"]["amount"] == 50000.0      # the rule's value survived
    assert d["slots"]["payee"] == "Rohan"       # the model added what rules missed


def test_a_failed_call_falls_back_to_the_baseline():
    bad = clu.CLUOutcome(called=True, reason="test", error="provider exploded")
    d = clu.merge_with_baseline("get_balance", 0.91, {"a": 1}, bad)
    assert d["intent"] == "get_balance" and d["source"] == "baseline"
    assert d["slots"] == {"a": 1}


# ---------------------------------------------------------------- routing

def test_confident_monolingual_turns_do_not_reach_the_model(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    call, why = clu.should_call(0.95, 0.60, 0.0, "What is my account balance", False)
    assert call is False and "confident" in why


def test_low_confidence_reaches_the_model(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.40, 0.50, 0.0, "the card thing", False)[0] is True


def test_a_close_run_between_two_intents_reaches_the_model(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.90, 0.02, 0.0, "balance and statement", False)[0] is True


def test_code_mixing_reaches_the_model(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.95, 0.9, 36.4, "Mera balance kitna hai and last three", False)[0]


def test_a_short_followup_reaches_the_model(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.95, 0.9, 0.0, "aur uske pehle wali?", True)[0] is True


def test_a_followup_phrase_with_no_conversation_does_not(monkeypatch):
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.95, 0.9, 0.0, "aur uske pehle wali?", False)[0] is False


def test_nothing_reaches_the_model_when_disabled(monkeypatch):
    """Explicitly disabled, not "whatever .env happens to say": this test used
    to assert the ambient default and started failing the moment a provider
    was configured."""
    monkeypatch.setattr(clu, "enabled", lambda: False)
    call, why = clu.should_call(0.01, 0.0, 99.0, "anything at all", True)
    assert call is False and why == "CLU disabled"


def test_enabled_follows_the_configured_provider(monkeypatch):
    monkeypatch.setattr("app.clu.CLU_PROVIDER", "null")
    assert clu.enabled() is False
    monkeypatch.setattr("app.clu.CLU_PROVIDER", "openai")
    assert clu.enabled() is True


# ---------------------------------------------------------------- providers

def test_every_provider_is_constructible():
    for name in provider_names():
        p = get_provider(name)
        assert isinstance(p.leaves_machine, bool)
        assert isinstance(p.available(), bool)


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="unknown CLU provider"):
        get_provider("definitely-not-a-provider")


def test_hosted_provider_declares_that_data_leaves_the_machine():
    assert OpenAICompatibleProvider().leaves_machine is True
    assert MockProvider().leaves_machine is False
    assert NullProvider().leaves_machine is False


def test_hosted_provider_without_a_key_fails_cleanly(monkeypatch):
    monkeypatch.delenv("BFSI_LLM_API_KEY", raising=False)
    reply = OpenAICompatibleProvider().complete("hello", None)
    assert reply.error and "not set" in reply.error
    assert reply.text == ""


def test_the_api_key_never_appears_in_a_provider_reply(monkeypatch):
    monkeypatch.setenv("BFSI_LLM_API_KEY", "sk-secret-do-not-leak")
    reply = OpenAICompatibleProvider().complete("hello", None)
    blob = json.dumps(reply.__dict__, default=str)
    assert "sk-secret-do-not-leak" not in blob


def test_mock_provider_reads_a_compound_code_mixed_request():
    reply = MockProvider().complete(
        "Mera balance kitna hai and last three transactions bhi bata do", None)
    r = CLUResult.model_validate(json.loads(reply.text))
    assert r.intent == "get_balance" and "mini_statement" in r.sub_intents
    assert r.code_mixed is True


# ---------------------------------------------------------------- malformed output

@pytest.mark.parametrize("text", [
    "", "I think they want their balance.", "{not json at all",
    '{"intent": "get_balance"',                      # truncated
    '{"intent": "rm -rf /", "language": "en", "confidence": 1}',
    '{"intent": "get_balance", "language": "klingon", "confidence": 1}',
])
def test_malformed_model_output_never_reaches_the_pipeline(monkeypatch, text):
    class Broken:
        name, leaves_machine = "broken", False
        def available(self): return True
        def complete(self, transcript, context):
            from app.clu.providers import ProviderReply
            return ProviderReply(text, "broken", "broken", 1.0, False)

    monkeypatch.setattr(clu, "enabled", lambda: True)
    monkeypatch.setattr("app.clu.get_provider", lambda name=None: Broken())
    out = clu.understand_turn("anything", baseline_confidence=0.1)
    assert out.result is None and out.error
    d = clu.merge_with_baseline("get_balance", 0.5, {}, out)
    assert d["intent"] == "get_balance" and d["source"] == "baseline"


def test_json_is_recovered_from_a_fenced_response(monkeypatch):
    class Fenced:
        name, leaves_machine = "fenced", False
        def available(self): return True
        def complete(self, transcript, context):
            from app.clu.providers import ProviderReply
            body = ('Sure! Here you go:\n```json\n'
                    '{"intent": "get_balance", "language": "hi", "confidence": 0.9}\n'
                    '```\nHope that helps.')
            return ProviderReply(body, "fenced", "fenced", 1.0, False)

    monkeypatch.setattr(clu, "enabled", lambda: True)
    monkeypatch.setattr("app.clu.get_provider", lambda name=None: Fenced())
    out = clu.understand_turn("mera balance", baseline_confidence=0.1)
    assert out.result is not None and out.result.intent == "get_balance"


def test_a_provider_that_raises_does_not_break_the_turn(monkeypatch):
    class Exploding:
        name, leaves_machine = "boom", False
        def available(self): return True
        def complete(self, transcript, context): raise RuntimeError("network on fire")

    monkeypatch.setattr(clu, "enabled", lambda: True)
    monkeypatch.setattr("app.clu.get_provider", lambda name=None: Exploding())
    out = clu.understand_turn("anything", baseline_confidence=0.1)
    assert out.result is None and "network on fire" in out.error


# ---------------------------------------------------------------- context

def test_conversation_context_is_bounded(monkeypatch):
    from app.config import CLU_CONTEXT_TURNS
    seen = {}

    class Recorder:
        name, leaves_machine = "rec", False
        def available(self): return True
        def complete(self, transcript, context):
            from app.clu.providers import ProviderReply
            seen["n"] = len(context or [])
            return ProviderReply('{"intent":"get_balance","language":"en","confidence":0.9}',
                                 "rec", "rec", 1.0, False)

    monkeypatch.setattr(clu, "enabled", lambda: True)
    monkeypatch.setattr("app.clu.get_provider", lambda name=None: Recorder())
    clu.understand_turn("aur?", context=[{"transcript": f"turn {i}"} for i in range(50)],
                        baseline_confidence=0.1)
    assert seen["n"] == CLU_CONTEXT_TURNS


# ---------------------------------------------------------------- trace

def test_outcome_serialises_for_the_trace():
    out = clu.CLUOutcome(called=True, reason="code-mixed", provider="openai",
                         model="llama-3.3-70b-versatile", latency_ms=412.0,
                         leaves_machine=True, prompt_tokens=310, completion_tokens=44,
                         result=CLUResult(intent="get_balance", language="code_mixed",
                                          languages=["hi", "en"], confidence=0.93))
    t = out.to_trace()
    assert t["data_left_the_machine"] is True
    assert t["prompt_version"] and t["model"] and t["latency_ms"] == 412.0
    assert t["result"]["intent"] == "get_balance"
    json.dumps(t)                                   # must be trace-serialisable


def test_rejected_output_is_truncated_in_the_trace():
    out = clu.CLUOutcome(called=True, reason="t", raw_rejected="x" * 10000)
    assert len(out.to_trace()["rejected_output"]) <= 300


def test_schema_enumerates_only_known_intents():
    from app.clu.schema import JSON_SCHEMA
    assert JSON_SCHEMA["properties"]["intent"]["enum"] == list(INTENTS)


# ---------------------------------------------------------------- compound routing

@pytest.mark.parametrize("text,expected", [
    ("Tell me my balance and also the IFSC of the Nigdi branch", True),
    ("Block my card and raise a dispute for the last transaction", True),
    ("Mera balance kitna hai aur last three transactions bhi bata do", True),
    ("Mala majha balance sanga and pan last transaction pan dakhva", True),
    # "and" joining a noun phrase is one ask, not two.
    ("What are the terms and conditions", False),
    ("Tell me about your terms and conditions please", False),
    ("What is my account balance", False),
    ("card", False),
])
def test_compound_requests_reach_the_model(monkeypatch, text, expected):
    """A single-label head cannot represent the second ask at ANY confidence,
    so neither the confidence nor the margin trigger fires on a compound
    request. Both compound failures in the first evaluation run were this."""
    monkeypatch.setattr(clu, "enabled", lambda: True)
    assert clu.should_call(0.95, 0.60, 0.0, text, False)[0] is expected


# ---------------------------------------------------------------- R4 crash

def test_a_string_amount_from_the_model_cannot_crash_the_turn():
    """Found by the latency harness on live audio, not by a unit test.

    The model is free to answer `"amount": "Rs 5,000"` and it does. That
    string used to reach dialogue.norm_amount, which compares it against
    zero, raising TypeError and killing the turn with a 500 in the middle of
    a call. Model output is untrusted input; it is coerced at the boundary
    and the money path is defensive as well, because it has several callers.
    """
    from app.clu.schema import CLUResult
    from app.pipeline.dialogue import norm_amount

    r = CLUResult(intent="fund_transfer", confidence=0.9,
                  entities={"amount": "Rs 5,000", "payee": "Diya"})
    assert r.entities["amount"] == 5000.0
    assert r.entities["payee"] == "Diya"

    # An amount that cannot be read as a number is dropped, not guessed at:
    # a wrong amount on a transfer is worse than a missing one, because a
    # missing one makes the assistant ask.
    assert "amount" not in CLUResult(intent="fund_transfer", confidence=0.9,
                                     entities={"amount": "a lot"}).entities
    assert "amount" not in CLUResult(intent="fund_transfer", confidence=0.9,
                                     entities={"amount": "-5"}).entities
    # A negative amount is dropped rather than made positive. An earlier
    # version of the coercion stripped the minus sign, turning "-5" into 5,
    # which is a wrong instruction rather than a missing one.
    assert "amount" not in CLUResult(intent="fund_transfer", confidence=0.9,
                                     entities={"amount": -5}).entities

    # And the money path degrades rather than raising, whatever reaches it.
    for bad in ("5000", "a lot", None, "", [], {}):
        assert isinstance(norm_amount(bad), float)
    assert norm_amount("5000") == norm_amount(5000)
