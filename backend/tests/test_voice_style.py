"""R5. Fillers and variation, with the forbidden cases pinned.

A filler makes a pause feel intentional. It is also the easiest way to make
a system sound like it is pretending to be human, and the worst place for it
is in the middle of six digits a caller is writing down. The rules are in
voice_style; these tests are what stop them drifting.
"""
import random

import pytest

from app.pipeline import voice_style as vs


def _rng(always=True):
    """A generator that always or never clears the rate limit, so the rule
    under test is the one being tested rather than luck."""
    class R(random.Random):
        def random(self): return 0.0 if always else 1.0
        def choice(self, seq): return seq[0]
    return R()


# ---------------------------------------------------------------- forbidden

@pytest.mark.parametrize("tier", [2, 3])
def test_no_filler_in_tier_two_or_three(tier):
    """Security-critical speech is always crisp."""
    out = vs.decorate("Your card is blocked.", lang="en", tier=tier, rng=_rng())
    assert out["used_filler"] is False


@pytest.mark.parametrize("text", [
    "Your OTP is 482913",
    "The card ending in 4321 is blocked",
    "Your balance is Rs 1,50,000",
    "I have transferred 5000 rupees",
    "आपका ओटीपी 482913 है",
])
def test_no_filler_anywhere_near_digits_or_money(text):
    out = vs.decorate(text, lang="en", tier=0, rng=_rng())
    assert out["used_filler"] is False, text


@pytest.mark.parametrize("decision", ["refused", "escalated"])
def test_no_filler_when_refusing_or_escalating(decision):
    out = vs.decorate("I cannot help with that.", lang="en", tier=0,
                      decision=decision, rng=_rng())
    assert out["used_filler"] is False


def test_no_filler_in_a_read_back():
    out = vs.decorate("Please confirm.", lang="en", tier=1, is_readback=True,
                      rng=_rng())
    assert out["used_filler"] is False


def test_no_filler_in_a_consent_or_recording_notice():
    notice = "This call is recorded for quality and compliance."
    assert vs.decorate(notice, lang="en", tier=0, rng=_rng())["used_filler"] is False


def test_never_two_turns_in_a_row():
    out = vs.decorate("Here is what I found.", lang="en", tier=0,
                      last_turn_had_filler=True, rng=_rng())
    assert out["used_filler"] is False


# ---------------------------------------------------------------- allowed

def test_a_filler_is_added_on_an_ordinary_turn():
    out = vs.decorate("Here is what I found.", lang="en", tier=0, rng=_rng())
    assert out["used_filler"] is True
    assert out["text"].endswith("Here is what I found.")
    assert len(out["text"]) > len("Here is what I found.")


def test_at_most_one_filler_per_turn():
    out = vs.decorate("Here is what I found.", lang="en", tier=0, rng=_rng())
    count = sum(out["text"].count(f) for f in vs.FILLERS["en"])
    assert count == 1


def test_the_rate_limit_actually_limits():
    """Roughly a third, not every turn."""
    rng = random.Random(7)
    used = sum(1 for _ in range(400)
               if vs.decorate("Here it is.", lang="en", tier=0,
                              rng=rng)["used_filler"])
    assert 0.2 < used / 400 < 0.5, used / 400


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_fillers_exist_in_every_language(lang):
    out = vs.decorate("Here is what I found.", lang=lang, tier=0, rng=_rng())
    assert out["used_filler"] and out["filler"] in vs.FILLERS[lang]


# ---------------------------------------------------------------- variation

@pytest.mark.parametrize("kind", list(vs.PHRASINGS))
@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_response_type_has_several_phrasings(kind, lang):
    assert len(vs.PHRASINGS[kind][lang]) >= 3


def test_a_phrasing_never_repeats_twice_in_a_row():
    rng = random.Random(3)
    last = None
    for _ in range(50):
        pick = vs.phrasing("anything_else", "en", avoid=last, rng=rng)
        assert pick != last
        last = pick


# ---------------------------------------------------------------- honesty

@pytest.mark.parametrize("question", [
    "are you a human", "Are you a real person?", "am i talking to a human",
    "is this a bot", "Are you an AI?",
])
def test_asking_whether_it_is_a_person_is_recognised(question):
    assert vs.asks_if_human(question), question


def test_it_says_it_is_automated_and_offers_a_person():
    """Natural is fine; pretending to be human is not. This is the same
    trust question the project is about."""
    for lang in ("en", "hi", "mr"):
        answer = vs.honest_answer(lang)
        assert answer and len(answer) > 20
    en = vs.honest_answer("en").lower()
    assert "automated" in en and "not a person" in en
    assert "colleague" in en or "someone" in en


def test_ordinary_questions_are_not_mistaken_for_the_human_question():
    for text in ("what is my balance", "are you able to block my card",
                 "is this account active"):
        assert not vs.asks_if_human(text), text
