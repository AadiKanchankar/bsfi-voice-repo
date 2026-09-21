"""A1. Code-switch-aware language identification.

Per-word language evidence is noisy. Left alone it produces labels that flip
every second word, which is useless to a compliance reviewer and useless to the
TTS voice selector. We smooth it with Viterbi over a language state machine
with a switch penalty:

    score(i, l) = log p_i(l) + max over l' [ score(i-1, l') - eta * 1[l != l'] ]

eta is the cost of changing language between adjacent words. At eta = 0 the
output is the raw argmax. As eta grows the tagger prefers longer runs, and in
the limit it collapses to a single language for the whole utterance. Backtrack
for the best path, then merge runs into LanguageSpan objects.

Complexity O(n |L|^2). At utterance length that is nothing.

The word-level evidence itself is a script and lexicon prior, not a trained LID
head, and the capability registry says so. The function signature takes
posteriors as an argument, so an ASR model that emits real per-word posteriors
drops in without touching the smoother.
"""
from __future__ import annotations

import math
import re
import unicodedata

from ..config import LANGID_FLOOR, LANGUAGES, SWITCH_PENALTY_ETA
from ..trace import LanguageSpan

# Function words carry the most language signal and are the words ASR gets
# right most often. Content words are left to the script prior.
_HI_WORDS = {
    "hai", "hain", "kya", "mera", "meri", "mujhe", "kitna", "kitne", "kitni",
    "bata", "batao", "do", "de", "dijiye", "karo", "karna", "kar", "nahi",
    "nahin", "aur", "bhi", "ka", "ki", "ke", "se", "me", "mein", "par", "ko",
    "yeh", "woh", "kaise", "kaun", "kab", "kahan", "chahiye", "paisa", "paise",
    "khata", "rupaye", "rupay", "hazaar", "lakh", "band", "karvana", "abhi",
    "है", "हैं", "क्या", "मेरा", "मेरी", "मुझे", "कितना", "कितने", "बताओ",
    "दो", "करो", "नहीं", "और", "भी", "का", "की", "के", "से", "में", "को",
    "यह", "वह", "कैसे", "कौन", "कब", "कहाँ", "चाहिए", "खाता", "रुपये", "बंद",
}
_MR_WORDS = {
    "aahe", "ahe", "kiti", "maza", "majha", "mala", "sanga", "sangaa", "kay",
    "kasa", "kashi", "kuthe", "ani", "pan", "hoy", "nahi_mr", "tumhi", "amhi",
    "band_kara", "khate", "rupaye_mr", "don", "saha", "paach", "havi", "havay",
    "आहे", "किती", "माझा", "माझी", "मला", "सांगा", "काय", "कसा", "कुठे",
    "आणि", "पण", "होय", "तुम्ही", "आम्ही", "खाते", "हवी", "हवं", "करा",
}
_EN_WORDS = {
    "the", "what", "is", "my", "are", "and", "how", "can", "you", "i", "me",
    "please", "tell", "show", "balance", "account", "card", "block", "loan",
    "interest", "rate", "rates", "transfer", "last", "three", "transactions",
    "statement", "cheque", "check", "branch", "ifsc", "number", "want", "to",
    "need", "help", "fraud", "someone", "has", "made", "on", "of", "for",
    "a", "an", "in", "it", "do", "does", "with", "from", "phone", "personal",
}


def _is_devanagari(word: str) -> bool:
    return any("DEVANAGARI" in unicodedata.name(ch, "") for ch in word if ch.isalpha())


def _is_perso_arabic(word: str) -> bool:
    """Whisper base sometimes writes Hindi in the Perso-Arabic script used for
    Urdu, which is the same spoken language for our purposes. Treating it as
    Latin script would make the tagger call it English, so it is mapped to the
    Hindi state and the trace note says the script was converted, not the
    language guessed. A larger ASR model does not do this; the capability note
    records that the demo default is `base`."""
    return any("ARABIC" in unicodedata.name(ch, "") for ch in word if ch.isalpha())


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w'ऀ-ॿ]+", text or "")


def word_posteriors(words: list[str], languages: list[str] | None = None) -> list[dict[str, float]]:
    """Per-word language posteriors from a script and lexicon prior.

    Replaceable: pass real posteriors straight to viterbi_smooth instead.
    """
    langs = languages or LANGUAGES
    out: list[dict[str, float]] = []
    for w in words:
        lw = w.lower()
        scores = {l: 0.15 for l in langs}     # uniform floor, nothing is impossible
        deva = _is_devanagari(w) or _is_perso_arabic(w)
        if deva:
            # Devanagari rules out English outright.
            scores["en"] = 0.01
            scores["hi"] = scores.get("hi", 0) + 0.4
            scores["mr"] = scores.get("mr", 0) + 0.4
        if lw in _HI_WORDS:
            scores["hi"] = scores.get("hi", 0) + 1.2
        if lw in _MR_WORDS:
            scores["mr"] = scores.get("mr", 0) + 1.2
        if lw in _EN_WORDS and not deva:
            scores["en"] = scores.get("en", 0) + 1.2
        if not deva and lw not in _HI_WORDS and lw not in _MR_WORDS and lw not in _EN_WORDS:
            # Unseen Latin-script token: mildly English, since the BFSI lexicon
            # (IFSC, NEFT, product names) is written in English everywhere.
            scores["en"] = scores.get("en", 0) + 0.35
        total = sum(scores.values())
        out.append({l: max(scores[l] / total, LANGID_FLOOR) for l in langs})
    return out


def viterbi_smooth(posteriors: list[dict[str, float]], eta: float = SWITCH_PENALTY_ETA,
                   languages: list[str] | None = None) -> list[str]:
    """Best language path under the switch penalty. Returns one label per word."""
    langs = languages or LANGUAGES
    n = len(posteriors)
    if n == 0:
        return []
    score = {l: math.log(max(posteriors[0].get(l, LANGID_FLOOR), LANGID_FLOOR)) for l in langs}
    back: list[dict[str, str]] = []
    for i in range(1, n):
        new_score: dict[str, float] = {}
        bp: dict[str, str] = {}
        for l in langs:
            best_prev, best_val = None, -math.inf
            for lp in langs:
                val = score[lp] - (eta if l != lp else 0.0)
                if val > best_val:
                    best_val, best_prev = val, lp
            new_score[l] = math.log(max(posteriors[i].get(l, LANGID_FLOOR), LANGID_FLOOR)) + best_val
            bp[l] = best_prev
        score, _ = new_score, back.append(bp)
    path = [max(score, key=score.get)]
    for bp in reversed(back):
        path.append(bp[path[-1]])
    return list(reversed(path))


def merge_spans(words: list[str], labels: list[str],
                posteriors: list[dict[str, float]]) -> list[LanguageSpan]:
    spans: list[LanguageSpan] = []
    i = 0
    while i < len(labels):
        j = i
        while j < len(labels) and labels[j] == labels[i]:
            j += 1
        conf = sum(posteriors[k].get(labels[i], 0.0) for k in range(i, j)) / (j - i)
        spans.append(LanguageSpan(lang=labels[i], start_word=i, end_word=j,
                                  text=" ".join(words[i:j]), confidence=round(conf, 4)))
        i = j
    return spans


def code_mix_index(labels: list[str]) -> float:
    """CMI = 100 * (1 - max_l(n_l) / n_total). 0 means monolingual."""
    n = len(labels)
    if n == 0:
        return 0.0
    counts: dict[str, int] = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    return round(100.0 * (1.0 - max(counts.values()) / n), 2)


def identify(text: str, eta: float = SWITCH_PENALTY_ETA,
             posteriors: list[dict[str, float]] | None = None) -> dict:
    """Full A1: tokenise, score, smooth, merge, report CMI."""
    words = tokenize(text)
    post = posteriors if posteriors is not None else word_posteriors(words)
    labels = viterbi_smooth(post, eta=eta)
    spans = merge_spans(words, labels, post)
    counts: dict[str, int] = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    dominant = max(counts, key=counts.get) if counts else "en"
    return {"words": words, "labels": labels, "spans": spans,
            "code_mix_index": code_mix_index(labels), "dominant": dominant,
            "counts": counts, "eta": eta}


def demo() -> None:
    mono = identify("What are your home loan interest rates")
    assert mono["dominant"] == "en" and mono["code_mix_index"] == 0.0, mono

    mixed = identify("Mera balance kitna hai and last three transactions bhi bata do")
    langs = {s.lang for s in mixed["spans"]}
    assert len(langs) > 1, mixed["labels"]
    assert mixed["code_mix_index"] > 0

    # The switch penalty must actually reduce the number of spans.
    noisy = [{"en": 0.55, "hi": 0.44, "mr": 0.01}, {"en": 0.45, "hi": 0.54, "mr": 0.01},
             {"en": 0.55, "hi": 0.44, "mr": 0.01}, {"en": 0.45, "hi": 0.54, "mr": 0.01}]
    assert len(set(viterbi_smooth(noisy, eta=0.0))) == 2
    assert len(set(viterbi_smooth(noisy, eta=3.0))) == 1
    print("langid ok", mixed["code_mix_index"], [(s.lang, s.text) for s in mixed["spans"]])


if __name__ == "__main__":
    demo()
