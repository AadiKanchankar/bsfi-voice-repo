"""A3, second half. Slot extraction by rule, not by model.

Rules are auditable, which is the whole point of this project. A compliance
officer can read the regular expression that pulled "fifty thousand" out of an
utterance. They cannot read a sequence tagger's weights.

Indian numbering is handled explicitly because "pachas hazaar" and "do lakh"
are how the amount is actually said, and an amount that parses wrong is the
single most dangerous failure mode in this system.
"""
from __future__ import annotations

import re

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
    # Hindi / Marathi, romanised.
    "ek": 1, "do": 2, "don": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5,
    "panch": 5, "paach": 5, "chhe": 6, "saha": 6, "saat": 7, "aath": 8,
    "nau": 9, "das": 10, "dus": 10, "pandhra": 15, "bees": 20, "vees": 20,
    "pachees": 25, "tees": 30, "chalis": 40, "pachas": 50, "pannas": 50,
    "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
}
_MULTIPLIERS = {
    "hundred": 100, "sau": 100, "shambhar": 100,
    "thousand": 1_000, "hazaar": 1_000, "hajar": 1_000, "k": 1_000,
    "lakh": 100_000, "lac": 100_000, "lakhs": 100_000,
    "crore": 10_000_000, "cr": 10_000_000,
}

_AMOUNT_DIGITS = re.compile(
    r"(?:rs\.?|inr|rupees?|rupaye|rupaya)?\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    r"(lakhs?|lac|crore|cr|thousand|hazaar|hajar|k)?", re.I)


def parse_amount(text: str) -> float | None:
    """Digits first, then word numbers. Returns None when no amount is present."""
    t = text.lower()
    best: float | None = None

    for m in _AMOUNT_DIGITS.finditer(t):
        raw, mult = m.group(1), m.group(2)
        if raw is None:
            continue
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        # A bare number with neither a currency cue nor a multiplier is not an
        # amount. It is a card's last four, a phone number, a cheque number or
        # a count of transactions, and guessing wrong here is the most
        # dangerous mistake this parser can make: it would put a phone number
        # into norm(amount) and into the risk score.
        # ponytail: strict rule, so "transfer 5000 to Rohan" extracts no amount
        # and the dialogue asks for it. Add a money-verb context rule if that
        # turns out to annoy people in testing.
        if mult is None and not re.search(r"(rs\.?|inr|rupee|rupaye|rupaya|₹)",
                                          t[max(0, m.start() - 12):m.end() + 12]):
            continue
        if mult:
            val *= _MULTIPLIERS[mult.lower()]
        best = val if best is None else max(best, val)
    if best is not None:
        return best

    words = re.findall(r"[a-z]+", t)
    total, current, seen = 0.0, 0.0, False
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
            seen = True
        elif w in _MULTIPLIERS and seen:
            m = _MULTIPLIERS[w]
            if m >= 1000:
                total += (current or 1) * m
                current = 0.0
            else:
                current = (current or 1) * m
        elif w in ("rupees", "rupaye", "rupaya", "rs"):
            continue
        elif seen and w not in ("and", "aur", "ani"):
            # The run of number words ended. Keep it only if a multiplier fired,
            # so "last three transactions" does not become an amount of 3.
            if total:
                break
            current, seen = 0.0, False
    value = total + (current if total else 0.0)
    return value if value > 0 else None


_LAST4 = re.compile(r"(?:ending(?:\s+(?:in|with))?|last\s*4|last\s+four|xx+|\*+)\s*(\d{4})\b", re.I)
_CARD_CTX = re.compile(r"card[^.\d]{0,20}(\d{4})\b", re.I)
_ACCT_CTX = re.compile(r"(?:account|khata|khate|a/c|acct)[^.\d]{0,20}(\d{4,18})\b", re.I)
_CHEQUE = re.compile(r"cheque\s*(?:number|no\.?|number)?\s*#?\s*(\d{4,8})\b", re.I)
_PAYEE = re.compile(
    r"(?:to|for|payee|beneficiary|named?|ko|la)\s+([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})?)")
_DATE_RANGE = re.compile(
    r"\b(last|past|previous)\s+(\d+|three|five|ten|seven|teen|paanch|saat)?\s*"
    r"(day|days|week|weeks|month|months|transaction|transactions|din|hafte|mahine)\b", re.I)

_WORD_COUNT = {"three": 3, "five": 5, "ten": 10, "seven": 7, "teen": 3,
               "paanch": 5, "saat": 7, "das": 10, "dus": 10, "two": 2, "do": 2}


def extract(text: str, intent: str | None = None) -> dict:
    """All slots for one utterance. Only non-empty slots are returned, so the
    trace shows exactly what was found and nothing that was guessed."""
    slots: dict = {}
    t = text or ""

    amount = parse_amount(t)
    if amount is not None:
        slots["amount"] = amount

    m = _LAST4.search(t)
    if m:
        slots["last4"] = m.group(1)
    m = _CARD_CTX.search(t)
    if m:
        slots["card_last4"] = m.group(1)[-4:]
    m = _ACCT_CTX.search(t)
    if m:
        slots["account_last4"] = m.group(1)[-4:]
    if "last4" in slots and "card_last4" not in slots and "account_last4" not in slots:
        key = "card_last4" if re.search(r"card", t, re.I) else "account_last4"
        slots[key] = slots.pop("last4")
    slots.pop("last4", None)

    m = _CHEQUE.search(t)
    if m:
        slots["cheque_number"] = m.group(1)

    m = _PAYEE.search(t)
    if m and intent in ("fund_transfer", "add_payee", None):
        name = m.group(1).strip()
        if name.lower() not in ("the", "my", "your"):
            slots["payee"] = name

    m = _DATE_RANGE.search(t)
    if m:
        n = m.group(2)
        count = int(n) if n and n.isdigit() else _WORD_COUNT.get((n or "").lower(), 3)
        unit = m.group(3).lower()
        slots["date_range"] = {"count": count, "unit": unit, "text": m.group(0)}

    for product in ("home loan", "car loan", "personal loan", "education loan",
                    "gold loan", "business loan", "fixed deposit", "credit card",
                    "debit card", "savings account", "current account",
                    "gruh karj", "personal loan"):
        if product in t.lower():
            slots["product"] = product
            break
    return slots


def demo() -> None:
    assert parse_amount("transfer fifty thousand rupees") == 50000
    assert parse_amount("pachas hazaar bhejna hai") == 50000
    assert parse_amount("Rs 25,000 transfer") == 25000
    assert parse_amount("send 2 lakh") == 200000
    assert parse_amount("do lakh ka NEFT") == 200000
    assert parse_amount("show me my last three transactions") is None, \
        parse_amount("show me my last three transactions")
    assert extract("block card ending 4321")["card_last4"] == "4321"
    assert extract("cheque number 456789 status")["cheque_number"] == "456789"
    assert extract("Transfer ten thousand to Rohan", "fund_transfer")["payee"] == "Rohan"
    assert extract("show my last three transactions")["date_range"]["count"] == 3
    print("slots ok")
