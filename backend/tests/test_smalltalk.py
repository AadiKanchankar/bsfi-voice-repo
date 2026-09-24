"""Turns that are not requests, and the refusal they used to get.

All three of these were observed in one recording, each answered with:

    "I do not have a verified answer to that, so I am not going to guess.
     The closest thing I have on file was not a close enough match."

Correct for an obscure policy question. Absurd as a reply to silence, to
"thank you", and to the exact phrase the assistant had just asked for.
"""
import pytest

from app import turn
from app.pipeline import smalltalk as st


# ---------------------------------------------------------------- blank

@pytest.mark.parametrize("text", ["", "   ", "\n\t", "...", "!!", None])
def test_silence_is_recognised_as_silence(text):
    assert st.is_blank(text) is True


def test_a_confident_transcript_is_not_blank():
    assert st.is_blank("what is my balance", 0.9) is False


def test_noise_with_near_zero_confidence_counts_as_unheard():
    """The recogniser returns an empty string for silence but sometimes a
    short hallucination for noise. Both mean "say that again"."""
    assert st.is_blank("uh", 0.001) is True


# ---------------------------------------------------------------- phrase

@pytest.mark.parametrize("text", [
    "my voice is my password",
    "My voice is my password.",
    "voice is my passcode",
    "मेरी आवाज़ ही मेरा पासवर्ड है",
    "माझा आवाज हाच माझा पासवर्ड आहे",
])
def test_the_voice_phrase_is_recognised(text):
    assert st.is_voice_phrase(text), text


def test_a_normal_request_is_not_the_voice_phrase():
    assert not st.is_voice_phrase("what is my password reset process")


# ---------------------------------------------------------------- courtesy

@pytest.mark.parametrize("text,kind", [
    ("thanks", "thanks"), ("Thank you.", "thanks"), ("ok", "thanks"),
    ("धन्यवाद", "thanks"), ("bye", "goodbye"), ("that's all", "goodbye"),
    ("no thanks", "goodbye"),
])
def test_courtesy_is_recognised(text, kind):
    assert st.is_pleasantry(text) == kind, text


def test_courtesy_does_not_swallow_a_request():
    """"thanks, now block my card" is a request. Answering it with "you are
    welcome" would be worse than the bug this replaces."""
    for text in ("thanks, now block my card", "ok what is my balance",
                 "thank you for that, can you transfer 500 rupees"):
        assert st.is_pleasantry(text) is None, text


# ---------------------------------------------------------------- end to end

@pytest.mark.slow
def test_an_empty_turn_asks_again_instead_of_refusing(live):
    s = turn.create_session(live, "CUST1000", device_id="pytest-blank")
    t = turn.run_turn(live, s["session_id"], text="")
    assert t.action_taken == "ask_again"
    assert t.decision == "clarify"
    assert "did not catch" in (t.reply_text or "")
    # The sentence that used to appear here.
    assert "not a close enough match" not in (t.reply_text or "")
    # And nothing was classified, because there was nothing to classify.
    assert t.intent is None


@pytest.mark.slow
def test_typing_the_voice_phrase_asks_for_the_microphone(live):
    """The assistant asked for this exact phrase one turn earlier, then
    refused it as an unknown request."""
    s = turn.create_session(live, "CUST1000", device_id="pytest-phrase")
    t = turn.run_turn(live, s["session_id"], text="My voice is my password.")
    assert t.action_taken == "need_spoken_phrase"
    assert "microphone" in (t.reply_text or "").lower()
    assert "not a close enough match" not in (t.reply_text or "")


@pytest.mark.slow
def test_thanking_it_does_not_get_a_refusal(live):
    s = turn.create_session(live, "CUST1000", device_id="pytest-thanks")
    t = turn.run_turn(live, s["session_id"], text="Thank you.")
    assert t.action_taken == "pleasantry_thanks"
    assert t.decision == "automated"
    assert "welcome" in (t.reply_text or "").lower()


@pytest.mark.slow
def test_a_real_request_still_goes_through_the_pipeline(live):
    """The guards must not swallow anything that is actually a request."""
    s = turn.create_session(live, "CUST1000", device_id="pytest-real")
    t = turn.run_turn(live, s["session_id"], text="What are your home loan interest rates")
    assert t.intent == "product_info"
    assert t.action_taken not in ("ask_again", "pleasantry_thanks",
                                  "need_spoken_phrase")


# ---------------------------------------------------------------- read-back

def test_the_read_back_is_a_sentence_when_the_last_four_are_unknown():
    """It used to say "the card ending on file", which is not English, on
    the one sentence a caller says yes to before a card is blocked."""
    from app.banking.actions import readback_summary
    en, hi, mr = readback_summary("block_card", {})
    assert "ending on file" not in en
    assert en.endswith("registered on your account.")
    for text in (en, hi, mr):
        assert text and text.strip().endswith((".", "।"))

    en4, _, _ = readback_summary("block_card", {"card_last4": "4321"})
    assert "ending four three two one" in en4


@pytest.mark.slow
def test_structured_input_is_not_mistaken_for_silence(live):
    """An OTP and a read-back confirmation arrive with no text at all,
    because the caller pressed a button. The first version of the blank
    guard swallowed them and broke the whole tier 2 flow.
    """
    from app.config import OTP_DEMO_CODE
    voice = "CUST1000_0.wav" if live.execute(
        "SELECT 1 FROM speakers WHERE customer_id='CUST1000'").fetchone() else None
    s = turn.create_session(live, "CUST1000", device_id="pytest-structured",
                            voice_clip=voice)
    turn.record_verification(live, s["session_id"], None, source="demo_clip")
    turn.run_turn(live, s["session_id"], text="Block my card")

    otp_turn = turn.run_turn(live, s["session_id"], otp=OTP_DEMO_CODE)
    assert otp_turn.action_taken != "ask_again", "the OTP was treated as silence"
    assert otp_turn.auth is not None and otp_turn.auth.otp_passed is True

    declined = turn.run_turn(live, s["session_id"], confirm=False)
    assert declined.action_taken == "readback_declined"
