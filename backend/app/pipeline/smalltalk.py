"""Turns that must not reach the intent classifier.

Three kinds of input were being run through the whole pipeline and coming
out the far end as the same grounding refusal:

    "I do not have a verified answer to that, so I am not going to guess.
     The closest thing I have on file was not a close enough match."

That sentence is correct for an obscure policy question. It is nonsense as a
reply to silence, to "thank you", and to the exact phrase the assistant
itself just asked the caller to say. All three were observed in one
recording.

The common fault: `run_turn` had no notion of a turn that is not a request.
An empty string has no intent, so the classifier returned `out_of_scope` at
0.0% confidence, retrieval found nothing above the floor, and the gate
refused on grounding. Every stage behaved correctly and the result was
absurd, which is the signature of a missing case rather than a broken one.

These are checked before classification and answered directly. Nothing here
touches risk, authentication or the gate: none of these turns can act.
"""
from __future__ import annotations

import re
import unicodedata

# The phrase the assistant asks callers to say for a voice check. Matched
# loosely because the caller is repeating it from memory, and because ASR
# will not return it verbatim.
_VOICE_PHRASE = re.compile(
    r"\b(my )?voice is my (password|passcode)\b"
    r"|मेरी आवाज़? ही मेरा पासवर्ड"
    r"|माझा आवाज हाच माझा पासवर्ड",
    re.IGNORECASE)

# Courtesy, not a request. Kept tight on purpose: "thanks, now block my
# card" is a request and must not be swallowed by a pleasantry reply.
_THANKS = re.compile(
    r"^\W*(thanks?|thank you|thankyou|ta|cheers|got it|okay|ok|alright|"
    r"perfect|great|lovely|nice one|धन्यवाद|शुक्रिया|ठीक है|अच्छा|"
    r"धन्यवाद्|बरं|ठीक आहे)"
    r"[\s!.,]*$",
    re.IGNORECASE)

_GOODBYE = re.compile(
    r"^\W*(bye|goodbye|good bye|that is all|that's all|nothing else|"
    r"no thanks|no thank you|अलविदा|बस इतना ही|नमस्ते|निरोप)"
    r"[\s!.,]*$",
    re.IGNORECASE)


def _clean(text: str) -> str:
    """Strip punctuation and marks, so "  ...  " counts as silence."""
    t = unicodedata.normalize("NFKC", text or "")
    return "".join(c for c in t if not unicodedata.category(c).startswith("P")
                   and not c.isspace())


def is_blank(text: str | None, asr_confidence: float | None = None) -> bool:
    """Nothing was said, or nothing intelligible was heard.

    Confidence is part of the test because the recogniser returns an empty
    string for silence but sometimes returns a short hallucination for
    noise, and both should be treated as "say that again".
    """
    if not _clean(text or ""):
        return True
    if asr_confidence is not None and asr_confidence < 0.05:
        return True
    return False


def is_voice_phrase(text: str) -> bool:
    return bool(_VOICE_PHRASE.search(text or ""))


def is_pleasantry(text: str) -> str | None:
    """`thanks`, `goodbye`, or None. Never a request."""
    if _GOODBYE.match(text or ""):
        return "goodbye"
    if _THANKS.match(text or ""):
        return "thanks"
    return None


# ---------------------------------------------------------------- replies

def blank_reply(lang: str) -> str:
    return {
        "en": "Sorry, I did not catch that. Could you say it again?",
        "hi": "माफ़ कीजिए, मैं सुन नहीं पाया। क्या आप दोबारा कह सकते हैं?",
        "mr": "माफ करा, मला ऐकू आले नाही. तुम्ही पुन्हा सांगाल का?",
    }.get(lang, "Sorry, I did not catch that. Could you say it again?")


def voice_phrase_typed_reply(lang: str) -> str:
    """They typed the phrase instead of saying it.

    A voice check needs a voice. Saying so is obvious and the system was
    not doing it: it refused the phrase as an unknown request, having asked
    for that exact phrase one turn earlier.
    """
    return {
        "en": ("I need to hear that rather than read it. Tap the microphone "
               "and say: my voice is my password."),
        "hi": ("मुझे यह पढ़ना नहीं, सुनना है। माइक्रोफ़ोन दबाइए और कहिए: "
               "मेरी आवाज़ ही मेरा पासवर्ड है।"),
        "mr": ("मला हे वाचायचे नाही, ऐकायचे आहे. मायक्रोफोन दाबा आणि म्हणा: "
               "माझा आवाज हाच माझा पासवर्ड आहे."),
    }.get(lang, "I need to hear that rather than read it.")


def pleasantry_reply(kind: str, lang: str) -> str:
    if kind == "goodbye":
        return {
            "en": "Thank you for calling. Goodbye.",
            "hi": "कॉल करने के लिए धन्यवाद। नमस्ते।",
            "mr": "फोन केल्याबद्दल धन्यवाद. नमस्कार.",
        }.get(lang, "Thank you for calling. Goodbye.")
    return {
        "en": "You are welcome. Anything else I can help with?",
        "hi": "आपका स्वागत है। और कुछ मदद चाहिए?",
        "mr": "आपले स्वागत आहे. आणखी काही मदत हवी आहे का?",
    }.get(lang, "You are welcome. Anything else I can help with?")
