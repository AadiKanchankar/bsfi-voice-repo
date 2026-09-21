"""The voice. Two things this file exists to stop regressing.

**Romanised Hindi.** Both engines phonemise from script, so "khatam hone
wale" is read with English vowels and comes out as neither Hindi nor English.
Every reply template is checked here, not just the ones a test happens to
exercise, because the failure is silent: the audio plays, it just sounds
wrong to anyone who speaks the language.

**Numbers read as database fields.** "206,465.68" spoken literally is the
other half of why the recording sounded robotic.
"""
import re

import pytest

from app.banking import actions
from app.pipeline import tts
from app.pipeline.speech_text import speak_friendly, speech_amount, speech_digits
from app.trace import ComplianceTrace

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def _all_reply_templates():
    """Every Reply dict the action layer can produce, with enough context to
    build it. Returns (label, reply_dict) pairs."""
    trace = ComplianceTrace(session_id="00000000-0000-0000-0000-000000000001",
                            turn_index=0,
                            consent_ref="00000000-0000-0000-0000-000000000002")
    trace.retrieval_max_score, trace.retrieval_floor = 0.2, 0.5
    out = [
        ("refuse", actions.refuse(trace, "test")["reply"]),
        ("out_of_scope", actions.out_of_scope(trace)["reply"]),
        ("escalate", actions.escalate(trace, "test")["reply"]),
        ("request_otp", actions.request_otp("block_card")["reply"]),
        ("need_verification", actions.need_verification()["reply"]),
        ("readback", actions.readback(*actions.readback_summary(
            "block_card", {"card_last4": "4321"}))["reply"]),
    ]
    for intent, slots in [("block_card", {"card_last4": "4321"}),
                          ("fund_transfer", {"amount": 50000, "payee": "Rohan"}),
                          ("limit_change", {"amount": 100000}),
                          ("other", {})]:
        en, hi, mr = actions.readback_summary(intent, slots)
        out.append((f"readback_summary:{intent}", {"en": en, "hi": hi, "mr": mr}))
    return out


@pytest.mark.parametrize("label,reply", _all_reply_templates(),
                         ids=[l for l, _ in _all_reply_templates()])
def test_hindi_and_marathi_templates_are_devanagari(label, reply):
    for lang in ("hi", "mr"):
        text = reply[lang]
        assert DEVANAGARI.search(text), f"{label}[{lang}] is romanised: {text[:70]!r}"


@pytest.mark.parametrize("label,reply", _all_reply_templates(),
                         ids=[l for l, _ in _all_reply_templates()])
def test_every_template_covers_all_three_languages(label, reply):
    assert set(reply) >= {"en", "hi", "mr"}
    for lang, text in reply.items():
        assert text.strip(), f"{label}[{lang}] is empty"


def test_consent_notice_is_devanagari():
    from app.turn import consent_notice
    notice = consent_notice()
    for lang in ("hi", "mr"):
        assert DEVANAGARI.search(notice[lang]), notice[lang]


def test_tts_refuses_to_speak_romanised_hindi():
    """The guard that makes the rule enforced rather than remembered."""
    with pytest.raises(ValueError, match="romanised"):
        tts.assert_devanagari("Aapke khate mein paise hain", "hi")
    with pytest.raises(ValueError):
        tts.assert_devanagari("Tumchya khatyat paise aahet", "mr")
    tts.assert_devanagari("आपके खाते में पैसे हैं", "hi")      # fine
    tts.assert_devanagari("Your balance is fine", "en")         # not checked


def test_tts_guard_tolerates_embedded_latin():
    """Names, reference codes and IFSC codes stay Latin inside a Hindi reply."""
    tts.assert_devanagari("मैंने Rohan को पैसे भेज दिए हैं।", "hi")
    tts.assert_devanagari("इसका कोड DEMO0001234 है।", "hi")


def test_amounts_are_spoken_not_printed():
    assert "," not in speech_amount(206465.68)
    assert speech_amount(50000) == "fifty thousand rupees"
    assert "लाख" in speech_amount(206465.68, "hi")


def test_identifiers_are_read_digit_by_digit():
    assert speech_digits("2902") == "two nine zero two"
    assert "हज़ार" not in speech_digits("2902", "hi")


def test_acronyms_are_spelled_out_for_the_synthesiser():
    assert speak_friendly("Your IFSC code") == "Your I F S C code"
    assert speak_friendly("Send by NEFT or UPI") == "Send by N E F T or U P I"


@pytest.mark.slow
@pytest.mark.parametrize("lang,text", [
    ("en", "Your savings account has fifty thousand rupees."),
    ("hi", "आपके बचत खाते में पचास हज़ार रुपये हैं।"),
    ("mr", "तुमच्या बचत खात्यात पन्नास हजार रुपये आहेत."),
])
def test_synthesis_produces_audio_in_every_language(lang, text):
    out = tts.synthesize(text, lang)
    assert out["available"], out.get("error")
    assert out["duration_s"] > 0.5
    assert out["engine"] in ("kokoro", "piper")
    assert len(out["audio"]) > 1000
