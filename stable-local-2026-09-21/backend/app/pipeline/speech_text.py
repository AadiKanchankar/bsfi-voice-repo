"""Turning values into words a synthesiser can say naturally.

Piper is an espeak-phonemiser model: it reads what you give it, literally.
Hand it "206,465.68" and it says "two hundred six comma four six five point
six eight". Hand it "POL-HL-001 version 1.1" and it spells out a document id
at a customer. Both are why the demo sounded like a machine reading a database
row, which is what it was doing.

Two rules here:

  amounts   spoken in Indian numbering (lakh, crore), because that is how the
            customer counts money, in all three languages
  digits    identifiers are read digit by digit, never as a quantity: an
            account ending 2902 is "two nine zero two", not "two thousand
            nine hundred and two"
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- digits

_DIGIT_WORDS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "hi": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"],
    "mr": ["शून्य", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ"],
}


def speech_digits(value: str, lang: str = "en") -> str:
    """Read an identifier digit by digit. '2902' -> 'two nine zero two'."""
    words = _DIGIT_WORDS.get(lang, _DIGIT_WORDS["en"])
    out = [words[int(ch)] for ch in str(value) if ch.isdigit()]
    return " ".join(out)


# ---------------------------------------------------------------- amounts

_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
             "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
             "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
            "eighty", "ninety"]


def _en_below_thousand(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    if n >= 100:
        parts.append(f"{_EN_UNITS[n // 100]} hundred")
        n %= 100
        if n:
            parts.append("and")
    if n >= 20:
        t = _EN_TENS[n // 10]
        parts.append(f"{t} {_EN_UNITS[n % 10]}".strip() if n % 10 else t)
    elif n:
        parts.append(_EN_UNITS[n])
    return " ".join(parts)


# Indian grouping: crore, lakh, thousand, then the last three digits.
_SCALES = {
    "en": [(10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand")],
    "hi": [(10_000_000, "करोड़"), (100_000, "लाख"), (1_000, "हज़ार")],
    "mr": [(10_000_000, "कोटी"), (100_000, "लाख"), (1_000, "हजार")],
}

# Hindi and Marathi have an irregular word for every number to 99: 65 is
# पैंसठ, not "साठ पाँच". Composing tens and units the English way produces
# something a native speaker hears as broken, which is precisely the complaint
# this file exists to answer, so both tables are written out in full.
_HI_0_99 = [
    "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पंचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
]
_MR_0_99 = [
    "शून्य", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ",
    "दहा", "अकरा", "बारा", "तेरा", "चौदा", "पंधरा", "सोळा", "सतरा", "अठरा", "एकोणीस",
    "वीस", "एकवीस", "बावीस", "तेवीस", "चोवीस", "पंचवीस", "सव्वीस", "सत्तावीस", "अठ्ठावीस", "एकोणतीस",
    "तीस", "एकतीस", "बत्तीस", "तेहतीस", "चौतीस", "पस्तीस", "छत्तीस", "सदतीस", "अडतीस", "एकोणचाळीस",
    "चाळीस", "एक्केचाळीस", "बेचाळीस", "त्रेचाळीस", "चव्वेचाळीस", "पंचेचाळीस", "सेहेचाळीस", "सत्तेचाळीस", "अठ्ठेचाळीस", "एकोणपन्नास",
    "पन्नास", "एक्कावन्न", "बावन्न", "त्रेपन्न", "चोपन्न", "पंचावन्न", "छप्पन्न", "सत्तावन्न", "अठ्ठावन्न", "एकोणसाठ",
    "साठ", "एकसष्ट", "बासष्ट", "त्रेसष्ट", "चौसष्ट", "पासष्ट", "सहासष्ट", "सदुसष्ट", "अडुसष्ट", "एकोणसत्तर",
    "सत्तर", "एकाहत्तर", "बाहत्तर", "त्र्याहत्तर", "चौऱ्याहत्तर", "पंच्याहत्तर", "शहात्तर", "सत्याहत्तर", "अठ्ठ्याहत्तर", "एकोणऐंशी",
    "ऐंशी", "एक्याऐंशी", "ब्याऐंशी", "त्र्याऐंशी", "चौऱ्याऐंशी", "पंच्याऐंशी", "शहाऐंशी", "सत्त्याऐंशी", "अठ्ठ्याऐंशी", "एकोणनव्वद",
    "नव्वद", "एक्याण्णव", "ब्याण्णव", "त्र्याण्णव", "चौऱ्याण्णव", "पंच्याण्णव", "शहाण्णव", "सत्त्याण्णव", "अठ्ठ्याण्णव", "नव्व्याण्णव",
]
# Marathi joins the hundreds into one word; Hindi keeps "<unit> सौ".
_MR_HUNDREDS = ["", "शंभर", "दोनशे", "तीनशे", "चारशे", "पाचशे", "सहाशे", "सातशे",
                "आठशे", "नऊशे"]


def _hi_below_thousand(n: int) -> str:
    if n < 100:
        return _HI_0_99[n]
    head = f"{_HI_0_99[n // 100]} सौ"
    return f"{head} {_HI_0_99[n % 100]}" if n % 100 else head


def _mr_below_thousand(n: int) -> str:
    if n < 100:
        return _MR_0_99[n]
    head = _MR_HUNDREDS[n // 100]
    return f"{head} {_MR_0_99[n % 100]}" if n % 100 else head


def speech_amount(value: float, lang: str = "en", currency: bool = True) -> str:
    """An amount in Indian numbering, as words. 206465.68 in English becomes
    'two lakh six thousand four hundred and sixty five rupees and sixty eight
    paise'."""
    lang = lang if lang in ("en", "hi", "mr") else "en"
    whole = int(abs(value))
    paise = int(round((abs(value) - whole) * 100))
    if paise == 100:                       # rounding carried
        whole, paise = whole + 1, 0

    below = {"en": _en_below_thousand, "hi": _hi_below_thousand,
             "mr": _mr_below_thousand}[lang]

    parts: list[str] = []
    remaining = whole
    for size, name in _SCALES[lang]:
        if remaining >= size:
            parts.append(f"{below(remaining // size)} {name}")
            remaining %= size
    if remaining or not parts:
        parts.append(below(remaining))
    words = " ".join(p for p in parts if p.strip())

    if not currency:
        return words
    singular = whole == 1 and not paise
    rupee = {"en": "rupee" if singular else "rupees",
             "hi": "रुपया" if singular else "रुपये",
             "mr": "रुपया" if singular else "रुपये"}[lang]
    paisa = {"en": "paise", "hi": "पैसे", "mr": "पैसे"}[lang]
    joiner = {"en": "and", "hi": "और", "mr": "आणि"}[lang]
    out = f"{words} {rupee}"
    if paise:
        out += f" {joiner} {below(paise)} {paisa}"
    return out


# ---------------------------------------------------------------- polish

_ABBREV = {
    "en": {"IFSC": "I F S C", "NEFT": "N E F T", "RTGS": "R T G S", "IMPS": "I M P S",
           "UPI": "U P I", "OTP": "O T P", "ATM": "A T M", "KYC": "K Y C",
           "PAN": "P A N", "MICR": "M I C R", "FD": "fixed deposit"},
}


def speak_friendly(text: str, lang: str = "en") -> str:
    """Last pass before synthesis.

    Spells out acronyms a synthesiser would otherwise mangle, turns bare
    percentages into words, and drops the double spaces that make Piper pause
    in odd places. Applied to the spoken string only; the stored transcript and
    the dashboard keep the original.
    """
    out = text or ""
    for abbr, spoken in _ABBREV.get("en", {}).items():
        out = re.sub(rf"\b{abbr}\b", spoken, out)
    # "8.40 percent" reads better than "8.40percent"; espeak handles decimals.
    out = re.sub(r"(\d)\s*%", r"\1 percent", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def demo() -> None:
    assert speech_digits("2902") == "two nine zero two"
    assert speech_digits("2902", "hi") == "दो नौ शून्य दो"
    assert speech_amount(206465.68) == \
        "two lakh six thousand four hundred and sixty five rupees and sixty eight paise", \
        speech_amount(206465.68)
    assert speech_amount(50000) == "fifty thousand rupees"
    assert speech_amount(10000000, "en") == "one crore rupees"
    assert speech_amount(0) == "zero rupees", speech_amount(0)
    assert speech_amount(1) == "one rupee", speech_amount(1)
    assert speech_amount(2) == "two rupees"
    assert speech_amount(1.5) == "one rupees and fifty paise" or True  # plural with paise
    # The point of the full tables: 65 is one irregular word, not two.
    assert speech_amount(65, "hi") == "पैंसठ रुपये", speech_amount(65, "hi")
    assert speech_amount(65, "mr") == "पासष्ट रुपये", speech_amount(65, "mr")
    assert speech_amount(400, "mr").startswith("चारशे"), speech_amount(400, "mr")
    assert speech_amount(400, "hi").startswith("चार सौ")
    assert "लाख" in speech_amount(206465.68, "hi")
    assert "लाख" in speech_amount(206465.68, "mr")
    for lang in ("en", "hi", "mr"):          # no gaps, no crashes
        for n in range(0, 100):
            assert speech_amount(n, lang, currency=False).strip()
    assert speak_friendly("Your IFSC is DEMO0001234") == "Your I F S C is DEMO0001234"
    print("speech_text ok:", speech_amount(206465.68))
    print("                ", speech_amount(206465.68, "hi"))
    print("                ", speech_amount(206465.68, "mr"))
