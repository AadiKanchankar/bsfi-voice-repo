"""A7. Exact-value tests for both checksums, plus the redaction contract."""
import pytest

from app.security import pii


@pytest.mark.parametrize("number,valid", [
    ("4539578763621486", True),      # Luhn valid
    ("4539578763621487", False),
    ("4111111111111111", True),
    ("5500005555555559", True),
    ("1234567890123456", False),
    ("79927398713", False),          # valid Luhn but too short for a card
])
def test_luhn(number, valid):
    assert pii.luhn_check(number) is valid


def test_luhn_checkdigit_round_trip():
    for partial in ["411111111111111", "453957876362148", "550000555555555"]:
        assert pii.luhn_check(partial + str(pii.luhn_checkdigit(partial)))


def test_verhoeff_known_values():
    # 236 with check digit 3 is the canonical worked example.
    assert pii.verhoeff_check("2363") is False          # wrong length for Aadhaar
    assert pii.verhoeff_checkdigit("236") == 3
    assert pii.verhoeff_checkdigit("12345") == 1


def test_verhoeff_round_trip_and_rejection():
    base = "23456789012"
    good = base + str(pii.verhoeff_checkdigit(base))
    assert pii.verhoeff_check(good)
    # Single digit change must fail, and so must a transposition.
    bad = good[:3] + str((int(good[3]) + 1) % 10) + good[4:]
    assert not pii.verhoeff_check(bad)
    swapped = good[:2] + good[3] + good[2] + good[4:]
    if swapped != good:
        assert not pii.verhoeff_check(swapped)


def test_random_12_digits_is_not_aadhaar():
    """The reason Verhoeff is here at all: without it every 12-digit number in
    a transcript would be tokenised as an Aadhaar number."""
    assert not pii.verhoeff_check("123456789012")
    out = pii.redact("the reference number is 123456789012")
    assert "AADHAAR" not in out.token_types.values()


def test_redacts_card_pan_phone_email():
    text = ("My card is 4539 5787 6362 1486, PAN ABCDE1234F, "
            "phone 9822012345, email demo.user@example.invalid")
    out = pii.redact(text)
    for leak in ["4539", "6362", "ABCDE1234F", "9822012345", "demo.user@example.invalid"]:
        assert leak not in out.text, out.text
    assert set(out.token_types.values()) == {"CARD", "PAN", "PHONE", "EMAIL"}


def test_tokens_are_stable_within_a_session():
    """<CARD_1> on turn 1 must still be <CARD_1> on turn 2, or the audit trail
    is a pile of unrelated tokens."""
    counters, seen = {}, {}
    a = pii.redact("card 4111111111111111 please", counters, seen)
    b = pii.redact("yes card 4111111111111111 again", counters, seen)
    assert list(a.token_types) == list(b.token_types) == ["<CARD_1>"]
    assert a.tokens == {"<CARD_1>": "4111111111111111"}
    assert b.tokens == {}, "a repeated value must not be vaulted twice"
    c = pii.redact("and card 4539578763621486 too", counters, seen)
    assert list(c.token_types) == ["<CARD_2>"]


def test_spoken_last_four_is_not_an_identifier():
    """A card's last four is deliberately shareable, and the tier 2 read-back
    says it back to the customer on purpose. Tokenising it made the assistant
    read out "the card ending ACCT one"."""
    out = pii.redact("please block the card ending four three two one")
    assert out.tokens == {}, out.tokens
    assert "four three two one" in out.text
    # And the written form is not redacted either, so both paths agree.
    assert pii.redact("block the card ending 4321").tokens == {}


def test_spoken_and_written_paths_agree_on_length():
    spoken = pii.redact("my account is four five six seven eight nine one two three")
    written = pii.redact("my account is 456789123")
    assert bool(spoken.tokens) == bool(written.tokens) is True


def test_spoken_digits_are_caught():
    out = pii.redact("my account number is four five six seven eight nine one two three")
    assert "four five" not in out.text
    assert any(t.startswith("<ACCT") for t in out.token_types)


def test_short_number_words_are_not_identifiers():
    out = pii.redact("show me my last three transactions")
    assert out.tokens == {}


def test_redaction_leaves_no_digits_from_an_account_number():
    out = pii.redact("transfer from account 123456789012345 now")
    assert "123456789012345" not in out.text
