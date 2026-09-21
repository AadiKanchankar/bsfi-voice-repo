"""A7. PII detection and tokenisation, run before anything touches disk.

Two checksum algorithms are implemented here rather than imported, because
both are short and both are the difference between a redactor that works and
one that fires on every twelve-digit number it sees:

  Luhn      card numbers
  Verhoeff  Aadhaar numbers

Order of detection matters. PAN is unambiguous and goes first. Aadhaar is
checked before generic account numbers so a valid twelve-digit Aadhaar is not
mislabelled, and card numbers are checked before account numbers for the same
reason. Anything that fails its checksum is not tokenised as that type, which
keeps false positives out of the vault.

Spoken digits are handled too. ASR writes "my account is four five six seven"
as words, and a redactor that only reads /\\d/ would let that straight through
to disk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- Luhn

def luhn_check(number: str) -> bool:
    """Mod-10 checksum. Double every second digit from the right, subtract 9
    from any result above 9, and the total must be divisible by 10."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 12:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def luhn_checkdigit(partial: str) -> int:
    """Check digit that makes `partial` + d a valid Luhn number. Used by the
    seed script so the synthetic cards genuinely exercise the redactor."""
    digits = [int(c) for c in partial if c.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:            # the appended digit shifts parity
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


# ---------------------------------------------------------------- Verhoeff

# Multiplication table of the dihedral group D5.
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
# Permutation applied at position i, repeating with period 8.
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_check(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) != 12:
        return False
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][d]]
    return c == 0


def verhoeff_checkdigit(partial: str) -> int:
    digits = [int(x) for x in partial if x.isdigit()]
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][d]]
    return _VERHOEFF_INV[c]


# ---------------------------------------------------------------- spoken digits

_DIGIT_WORDS: dict[str, str] = {}
for _lang_map in (
    # English, including the "oh" that ASR produces for a spoken zero.
    {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
     "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"},
    # Hindi, romanised and Devanagari.
    {"shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
     "paanch": "5", "panch": "5", "chhe": "6", "che": "6", "saat": "7",
     "aath": "8", "nau": "9",
     "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5",
     "पाँच": "5", "छह": "6", "सात": "7", "आठ": "8", "नौ": "9"},
    # Marathi where it differs from Hindi.
    {"don": "2", "paach": "5", "saha": "6", "दोन": "2", "सहा": "6"},
):
    _DIGIT_WORDS.update(_lang_map)

_MULTIPLIER_WORDS = {"double": 2, "triple": 3}
# Match the written patterns: the shortest identifier any of them accepts is a
# 9-digit account number. A shorter spoken run is a card's last four, a PIN
# length, a cheque number or a year, and tokenising those made the spoken path
# stricter than the written one for no benefit. It also broke the tier 2
# read-back, which exists precisely to say a card's last four back to the
# customer and was reading out "the card ending ACCT one".
MIN_SPOKEN_DIGITS = 9


def spoken_digits_to_string(words: list[str]) -> str:
    out = []
    pending = 1
    for w in words:
        key = w.lower().strip(".,")
        if key in _MULTIPLIER_WORDS:
            pending = _MULTIPLIER_WORDS[key]
            continue
        out.append(_DIGIT_WORDS[key] * pending)
        pending = 1
    return "".join(out)


def find_spoken_digit_runs(text: str) -> list[tuple[int, int, str]]:
    """Returns (char_start, char_end, digits) for runs of >= MIN_SPOKEN_DIGITS
    consecutive digit words."""
    runs: list[tuple[int, int, str]] = []
    tokens = [(m.group(0), m.start(), m.end())
              for m in re.finditer(r"[^\s]+", text)]
    i = 0
    while i < len(tokens):
        word = tokens[i][0].lower().strip(".,?!")
        if word in _DIGIT_WORDS or word in _MULTIPLIER_WORDS:
            j = i
            run_words = []
            while j < len(tokens):
                w = tokens[j][0].lower().strip(".,?!")
                if w in _DIGIT_WORDS or w in _MULTIPLIER_WORDS:
                    run_words.append(w)
                    j += 1
                else:
                    break
            digits = spoken_digits_to_string(run_words)
            if len(digits) >= MIN_SPOKEN_DIGITS:
                runs.append((tokens[i][1], tokens[j - 1][2], digits))
            i = j
        else:
            i += 1
    return runs


# ---------------------------------------------------------------- detection

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PAN",     re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("EMAIL",   re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("CARD",    re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")),
    ("PHONE",   re.compile(r"(?:\+?91[ -]?)?\b[6-9]\d{9}\b")),
    ("ACCT",    re.compile(r"\b\d{9,18}\b")),
]


@dataclass
class Redaction:
    text: str
    tokens: dict[str, str] = field(default_factory=dict)        # token -> raw value
    token_types: dict[str, str] = field(default_factory=dict)   # token -> type


def _validates(kind: str, raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if kind == "CARD":
        return luhn_check(digits)
    if kind == "AADHAAR":
        return verhoeff_check(digits)
    if kind == "PHONE":
        return len(digits) in (10, 12)
    if kind == "ACCT":
        return 9 <= len(digits) <= 18
    return True


def redact(text: str, counters: dict[str, int] | None = None,
           seen: dict[str, str] | None = None) -> Redaction:
    """Replace every detected identifier with a stable token.

    `counters` and `seen` are the caller's per-session state. Passing the same
    two dicts across the turns of one session is what makes <ACCT_1> mean the
    same account on turn 5 as it did on turn 1, which is the difference between
    a readable audit trail and a pile of unrelated tokens.

    `tokens` on the result holds only what this call newly discovered, so a
    caller can vault exactly the new values rather than rewriting the vault.
    """
    if not text:
        return Redaction(text=text or "")
    counters = counters if counters is not None else {}
    seen = seen if seen is not None else {}
    result = Redaction(text=text)
    spans: list[tuple[int, int, str, str]] = []

    for kind, pat in PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(0)
            if not _validates(kind, raw):
                continue
            spans.append((m.start(), m.end(), kind, raw))
    for start, end, digits in find_spoken_digit_runs(text):
        kind = "CARD" if luhn_check(digits) else ("AADHAAR" if verhoeff_check(digits) else "ACCT")
        spans.append((start, end, kind, text[start:end]))

    # Longest match wins on overlap, then earliest. A card number must not be
    # partially eaten by the account-number pattern.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen: list[tuple[int, int, str, str]] = []
    last_end = -1
    for s in spans:
        if s[0] >= last_end:
            chosen.append(s)
            last_end = s[1]

    out, cursor = [], 0
    for start, end, kind, raw in chosen:
        norm = raw.strip()
        if norm in seen:
            token = seen[norm]
            result.token_types[token] = kind
        else:
            counters[kind] = counters.get(kind, 0) + 1
            token = f"<{kind}_{counters[kind]}>"
            seen[norm] = token
            result.tokens[token] = norm
            result.token_types[token] = kind
        out.append(text[cursor:start])
        out.append(token)
        cursor = end
    out.append(text[cursor:])
    result.text = "".join(out)
    return result


def last4(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    return digits[-4:] if len(digits) >= 4 else digits


def demo() -> None:
    assert luhn_check("4539578763621486")
    assert not luhn_check("4539578763621487")
    assert verhoeff_check("234567890124") == (verhoeff_checkdigit("23456789012") == 4)
    n = "23456789012"
    assert verhoeff_check(n + str(verhoeff_checkdigit(n)))
    r = redact("My card 4539 5787 6362 1486 and PAN ABCDE1234F, call 9822012345")
    assert "4539" not in r.text and "ABCDE1234F" not in r.text, r.text
    assert set(r.token_types.values()) >= {"CARD", "PAN", "PHONE"}
    counters, seen = {}, {}
    x1 = redact("card 4111111111111111", counters, seen)
    x2 = redact("that card 4111111111111111 again", counters, seen)
    assert list(x1.token_types) == list(x2.token_types) == ["<CARD_1>"]
    assert x2.tokens == {}, "a repeat must not be re-vaulted"
    r2 = redact("my account is four five six seven eight nine one two three")
    assert "four five" not in r2.text and "<ACCT_1>" in r2.text, r2.text
    # A random 12-digit string must not be mistaken for an Aadhaar number.
    assert not verhoeff_check("123456789012")
    print("pii ok", r.text)


if __name__ == "__main__":
    demo()
