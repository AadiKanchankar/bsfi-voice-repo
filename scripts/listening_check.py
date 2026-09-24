"""R5. Render the before and after voices for a blind listening check.

The change request asks the team to compare the old voice with the new one
and note the result in RESULTS.md. This produces the material for that, in a
form where the listener cannot tell which is which until afterwards.

What differs between A and B is the spoken-text normaliser, which is the
change R5 actually made to how things are pronounced: amounts in the Indian
system, codes spelled out, digits in groups. The voice model is the same in
both, so the comparison isolates the thing that was changed rather than
measuring two unrelated differences at once.

    python scripts/listening_check.py

Writes pairs into listening-check/ and a scoring sheet next to them. The
file names are deliberately opaque: a listener who can see "before" and
"after" in the filename is not running a blind test.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline import tts                                   # noqa: E402
from app.pipeline.speech_text import normalise_for_speech      # noqa: E402

# Deliberately not under runtime/. A scenario test asserts that no plaintext
# audio exists anywhere in the runtime directory, which is a blunt instrument
# and a good one: it caught these files the first time this script ran. These
# samples are six fixed sentences from a script in the repository and contain
# no caller data, but the right response to a useful assertion is to stay out
# of its way rather than to narrow it.
OUT = ROOT / "listening-check"

# Lines chosen because each one contains something the normaliser changes.
# A pair that sounds identical teaches the listener nothing.
LINES = [
    ("en", "Your balance is Rs. 1,50,000 and your last payment was 2500 rupees."),
    ("en", "Your IFSC is SBIN0005943 and the card ending in 4321 is now blocked."),
    ("en", "Your OTP is 482913. It expires in ten minutes."),
    ("hi", "आपका बैलेंस 150000 रुपये है।"),
    ("hi", "आपका ओटीपी 482913 है।"),
    ("mr", "तुमचा बॅलन्स 206465.68 रुपये आहे."),
]


def render(text: str, lang: str, normalised: bool) -> bytes:
    # `synthesize` already normalises through speak_friendly, so the "before"
    # side has to bypass it to be a real comparison rather than two identical
    # files with different names.
    spoken = normalise_for_speech(text, lang) if normalised else text
    from app.pipeline.tts import _speak_kokoro, _speak_piper, engine
    out = (_speak_kokoro(spoken, lang) if engine() != "piper" else None) \
        or _speak_piper(spoken, lang)
    return out["audio"] if out else b""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260921)
    sheet = []

    for i, (lang, text) in enumerate(LINES, start=1):
        pair = {"before": render(text, lang, False),
                "after": render(text, lang, True)}
        # Randomise which side is A, so the order carries no information.
        first = rng.choice(["before", "after"])
        second = "after" if first == "before" else "before"
        tag = hashlib.sha256(f"{i}{text}".encode()).hexdigest()[:8]
        for label, which in (("A", first), ("B", second)):
            path = OUT / f"{tag}_{label}.wav"
            path.write_bytes(pair[which])
        sheet.append({"pair": tag, "language": lang, "text": text,
                      "A": first, "B": second})
        print(f"{tag}  {lang}  {text[:52]}")

    (OUT / "answers.json").write_text(json.dumps(sheet, indent=2, ensure_ascii=False))

    lines = [
        "# Blind listening check", "",
        "Six pairs. For each one, play A then B and answer three questions.",
        "Do not open `answers.json` until every row is filled in: it says which",
        "side is which, and knowing that makes the result worthless.", "",
        "| pair | which is clearer? (A/B/same) | which sounds more natural? | "
        "did either mispronounce a number or code? |",
        "|---|---|---|---|",
    ]
    lines += [f"| `{r['pair']}` | | | |" for r in sheet]
    lines += [
        "", "## Then",
        "",
        "Count the pairs where the normalised side won on clarity. Put the",
        "count and the number of listeners in RESULTS.md. If the normalised",
        "side does not win, say that instead: a change that does not help is",
        "worth knowing about, and this project does not print numbers it did",
        "not measure.",
        "",
        "Listen on the laptop speakers you will demo with. A good pair of",
        "headphones will make both sides sound better than the room will.",
    ]
    (OUT / "scoring_sheet.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {len(sheet)} pairs to {OUT}")
    print("scoring sheet:", OUT / "scoring_sheet.md")


if __name__ == "__main__":
    main()
