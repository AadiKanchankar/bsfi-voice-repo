"""R5. What the assistant actually says, spelled out.

Most "wrong pronunciation" in banking is not the voice model. It is a
synthesiser reading 150000 in the western grouping, pronouncing an IFSC code
as a word, or running a card's last four digits together into one number. All
of that is fixed before the audio engine sees the text.

These tests pin the exact spoken string, per language, because "sounds about
right" is not a thing a test can check and a regression here is inaudible to
anyone reading the code.
"""
import pytest

from app.pipeline.speech_text import (normalise_for_speech, speech_amount,
                                      speech_digits, spell_code)
from app.pipeline.tts import assert_devanagari


# ---------------------------------------------------------------- amounts

@pytest.mark.parametrize("text,lang,expected", [
    ("Your balance is Rs. 1,50,000 today", "en",
     "Your balance is one lakh fifty thousand rupees today"),
    ("Rs 25,000 has been transferred", "en",
     "twenty five thousand rupees has been transferred"),
    ("I sent 5000 rupees", "en", "I sent five thousand rupees"),
    ("₹2,00,000 approved", "en", "two lakh rupees approved"),
    ("INR 1 is the fee", "en", "one rupee is the fee"),
])
def test_rupee_amounts_are_read_in_the_indian_system(text, lang, expected):
    assert normalise_for_speech(text, lang) == expected


def test_lakh_and_crore_not_thousands_of_thousands(text=None):
    """The whole point of the Indian grouping. 150000 is one lakh fifty
    thousand, never one hundred fifty thousand."""
    out = normalise_for_speech("Rs 1,50,000", "en")
    assert "lakh" in out and "hundred fifty thousand" not in out
    assert normalise_for_speech("Rs 1,00,00,000", "en") == "one crore rupees"


def test_paise_are_spoken_when_present():
    assert normalise_for_speech("Rs 206465.68 available", "en") == (
        "two lakh six thousand four hundred and sixty five rupees "
        "and sixty eight paise available")


# ---------------------------------------------------------------- codes

def test_an_ifsc_is_read_letter_by_letter():
    assert spell_code("DEMO0001234") == "D E M O zero zero zero one two three four"
    assert normalise_for_speech("Your IFSC is SBIN0005943", "en") == (
        "Your IFSC is S B I N zero zero zero five nine four three")


def test_a_code_in_hindi_is_spelled_in_devanagari():
    """The code is Latin on screen. Spoken as Latin it would go through the
    Hindi phonemiser with English vowels and come out as noise, so the letter
    names are Devanagari."""
    out = normalise_for_speech("आपका IFSC कोड SBIN0005943 है", "hi")
    assert "एस बी आई एन" in out, out
    assert "SBIN" not in out
    assert_devanagari(out, "hi")          # must not raise


# ---------------------------------------------------------------- digits

def test_masked_digits_are_read_in_small_groups():
    """Eight digits in one breath cannot be written down. Two at a time can."""
    assert normalise_for_speech("card XXXXXX2345 is blocked", "en") == (
        "card two three, four five is blocked")
    assert normalise_for_speech("the card ending in 4321 is blocked", "en") == (
        "the card ending in four three, two one is blocked")


@pytest.mark.parametrize("lang,expected", [
    ("en", "four, eight, two, nine, one, three"),
    ("hi", "चार, आठ, दो, नौ, एक, तीन"),
    ("mr", "चार, आठ, दोन, नऊ, एक, तीन"),
])
def test_an_otp_is_one_digit_at_a_time_with_pauses(lang, expected):
    """Never grouped. A caller is typing these in as they hear them."""
    prompt = {"en": "Your OTP is 482913", "hi": "आपका ओटीपी 482913 है",
              "mr": "तुमचा ओटीपी 482913 आहे"}[lang]
    assert expected in normalise_for_speech(prompt, lang)


def test_the_hindi_keyword_matches_despite_its_combining_vowel():
    """`ओटीपी` ends in a combining vowel sign, which is not a word character,
    so a regex written with \\b silently matched nothing in Hindi while
    working perfectly in English."""
    assert "482913" not in normalise_for_speech("आपका ओटीपी 482913 है", "hi")


# ---------------------------------------------------------------- scripts

@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_nothing_the_normaliser_emits_breaks_the_script_guard(lang):
    samples = {
        "hi": ["आपका बैलेंस 150000 रुपये है", "आपका ओटीपी 482913 है",
               "आपका IFSC कोड DEMO0001234 है", "कार्ड XXXXXX2345 ब्लॉक है"],
        "mr": ["तुमचा बॅलन्स 206465.68 रुपये आहे", "तुमचा ओटीपी 482913 आहे",
               "तुमचा IFSC कोड DEMO0001234 आहे"],
    }[lang]
    for text in samples:
        assert_devanagari(normalise_for_speech(text, lang), lang)


def test_ordinary_text_is_left_alone():
    """A normaliser that rewrites things it should not is worse than none."""
    for text in ("Your account is active.",
                 "I can help with that.",
                 "आपका खाता सक्रिय है।"):
        lang = "hi" if "आपका" in text else "en"
        assert normalise_for_speech(text, lang) == text


def test_digits_and_amounts_agree_with_each_other():
    assert speech_digits("2902") == "two nine zero two"
    assert speech_amount(1) == "one rupee"
    assert speech_amount(2) == "two rupees"
