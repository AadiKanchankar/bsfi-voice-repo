"""R5. Variation and fillers, under rules.

Two separate problems, both about the assistant sounding like a recording.

**Variation.** Saying the identical sentence every time is the single most
robotic thing a helpline can do. Each response type carries several
phrasings, rotated, and the same one never comes up twice in a row on one
call.

**Fillers.** A short "let me check that" is what a person says while they
look something up, and it makes the pause feel intentional rather than
broken. It is also the easiest way to make a system sound like it is
pretending to be human, so the rules are strict and enforced here rather
than left to whoever writes the next reply:

- at most one filler in a turn,
- in roughly a third of eligible turns,
- never twice in a row,
- and never at all in security-critical speech.

**What "security-critical" means, concretely.** Any turn at tier 2 or tier 3,
any read-back, any consent or legal notice, any refusal, and any text
containing an amount, an account or card number, or a one time password. A
caller writing down six digits does not need the assistant sounding
thoughtful in the middle of them. The test suite asserts each of these
rather than trusting the list to stay true.

**Natural is fine; pretending to be human is not.** None of this makes the
assistant claim to be a person. Asked directly, it says it is an automated
assistant and offers a human, and that is a test too.
"""
from __future__ import annotations

import random
import re

# Roughly a third of eligible turns, as the change request specifies.
FILLER_RATE = 0.33

# Short, neutral, and clearly conversational glue rather than content.
FILLERS = {
    "en": ["Let me check that for you.", "One moment.", "Right, let me look."],
    "hi": ["मैं यह देखता हूँ।", "एक क्षण।", "ठीक है, मैं देखता हूँ।"],
    "mr": ["मी हे तपासतो.", "एक क्षण.", "ठीक आहे, मी बघतो."],
}

# Phrasings per response type. Three to five each, rotated.
PHRASINGS = {
    "greeting": {
        "en": ["How can I help you today?", "What can I do for you?",
               "How may I help?"],
        "hi": ["मैं आपकी कैसे मदद कर सकता हूँ?", "आपके लिए क्या कर सकता हूँ?",
               "बताइए, कैसे मदद करूँ?"],
        "mr": ["मी तुमची कशी मदत करू शकतो?", "तुमच्यासाठी काय करू शकतो?",
               "सांगा, कशी मदत करू?"],
    },
    "acknowledge": {
        "en": ["Certainly.", "Of course.", "Sure."],
        "hi": ["ज़रूर।", "बिलकुल।", "ठीक है।"],
        "mr": ["नक्कीच.", "अर्थात.", "ठीक आहे."],
    },
    "anything_else": {
        "en": ["Is there anything else I can help with?",
               "Anything else today?", "Can I help with anything else?"],
        "hi": ["क्या मैं और किसी चीज़ में मदद कर सकता हूँ?", "और कुछ?",
               "कुछ और मदद चाहिए?"],
        "mr": ["आणखी काही मदत करू का?", "आणखी काही?", "दुसरे काही हवे आहे का?"],
    },
}

# Text that must be spoken crisply, whatever the tier says.
_DIGIT_RUN = re.compile(r"\d{3,}")
_MONEY = re.compile(r"(?:Rs\.?|INR|₹)\s*\d|\d\s*(?:rupees?|रुपये|रुपया)", re.IGNORECASE)
_SENSITIVE_WORDS = re.compile(
    r"\b(?:OTP|one time password|password|read ?back|confirm|consent|"
    r"recorded|refuse|refused|cannot|unable)\b|ओटीपी|पुष्टि|सहमति",
    re.IGNORECASE)


def is_sensitive(text: str) -> bool:
    """Speech that must stay crisp regardless of the turn's tier."""
    t = text or ""
    return bool(_DIGIT_RUN.search(t) or _MONEY.search(t)
                or _SENSITIVE_WORDS.search(t))


def may_use_filler(*, tier: int | None, decision: str | None, text: str,
                   last_turn_had_filler: bool, is_readback: bool = False) -> bool:
    """Every rule in one place, so the answer is checkable rather than a
    judgement made at each call site."""
    if last_turn_had_filler:
        return False
    if is_readback:
        return False
    if tier is not None and tier >= 2:
        return False
    if decision in ("refused", "escalated"):
        return False
    return not is_sensitive(text)


def pick_filler(lang: str, rng: random.Random | None = None) -> str | None:
    """A filler, or None for the roughly two thirds of turns that get none."""
    rng = rng or random
    if rng.random() > FILLER_RATE:
        return None
    return rng.choice(FILLERS.get(lang, FILLERS["en"]))


def phrasing(kind: str, lang: str, *, avoid: str | None = None,
             rng: random.Random | None = None) -> str:
    """One of several phrasings, never the one used last time.

    `avoid` is the previous choice on this call. With three options and one
    excluded there are always two left, so this never has to repeat itself.
    """
    rng = rng or random
    options = PHRASINGS[kind].get(lang) or PHRASINGS[kind]["en"]
    choices = [o for o in options if o != avoid] or options
    return rng.choice(choices)


def decorate(text: str, *, lang: str, tier: int | None = None,
             decision: str | None = None, last_turn_had_filler: bool = False,
             is_readback: bool = False, rng: random.Random | None = None) -> dict:
    """Return the text to speak and whether a filler was added.

    The caller records `used_filler` on the session so the next turn knows
    not to add another. Returning it rather than hiding it is what makes the
    "never twice in a row" rule testable.
    """
    if not may_use_filler(tier=tier, decision=decision, text=text,
                          last_turn_had_filler=last_turn_had_filler,
                          is_readback=is_readback):
        return {"text": text, "used_filler": False, "reason": "not eligible"}
    filler = pick_filler(lang, rng)
    if not filler:
        return {"text": text, "used_filler": False, "reason": "rate limit"}
    return {"text": f"{filler} {text}".strip(), "used_filler": True,
            "filler": filler, "reason": "eligible"}


# ---------------------------------------------------------------- honesty

AM_I_HUMAN = re.compile(
    # "an AI" as well as "a bot": the article changes and the question does
    # not, which is the sort of thing that makes a guard look like it works.
    r"\b(are you (an?\s+)?(human|person|real|bot|robot|machine|ai|"
    r"real person|computer)|"
    r"am i (talking|speaking) to (an?\s+)?(human|person|real person|bot|machine)|"
    r"is (this|that) (an?\s+)?(human|person|bot|robot|recording|machine))\b"
    r"|क्या आप (इंसान|व्यक्ति|रोबोट|मशीन)|तुम्ही (माणूस|व्यक्ती|रोबोट) आहात",
    re.IGNORECASE)

HONEST_ANSWER = {
    "en": ("I am an automated assistant, not a person. I can put you through "
           "to a colleague if you would prefer to speak to someone."),
    "hi": ("मैं एक स्वचालित सहायक हूँ, कोई व्यक्ति नहीं। अगर आप किसी व्यक्ति से "
           "बात करना चाहें तो मैं जोड़ सकता हूँ।"),
    "mr": ("मी एक स्वयंचलित सहाय्यक आहे, व्यक्ती नाही. तुम्हाला कोणाशी बोलायचे "
           "असल्यास मी जोडून देतो."),
}


def asks_if_human(text: str) -> bool:
    return bool(AM_I_HUMAN.search(text or ""))


def honest_answer(lang: str) -> str:
    """Never hedge this one. It is the same trust question the project is
    about, and an assistant that dodges it has failed the premise."""
    return HONEST_ANSWER.get(lang, HONEST_ANSWER["en"])
