#!/usr/bin/env python3
"""Render the labelled evaluation utterances to audio with Piper.

The audio is synthetic. That is stated in data/eval/utterances.json, in
RESULTS.md and here. WER measured on it is optimistic relative to human
telephony audio, and the point of measuring it anyway is the entity-level
error rate: the relative ranking of entity types holds even when the absolute
WER is flattering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import EVAL_DIR       # noqa: E402

AUDIO_DIR = EVAL_DIR / "audio"
# Hindi, Marathi and code-mixed lines are rendered with the Hindi voice; there
# is no Marathi Piper voice, which is recorded in docs/STACK_MAPPING.md.
VOICE_FOR_LANG = {"en": "en_US-amy-medium", "hi": "hi_IN-pratham-medium",
                  "mr": "hi_IN-pratham-medium", "mix": "hi_IN-pratham-medium"}


def main() -> int:
    data = json.loads((EVAL_DIR / "utterances.json").read_text(encoding="utf-8"))
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    import io
    import wave

    from piper import PiperVoice

    from app.pipeline.tts import VOICE_DIR

    cache: dict[str, object] = {}
    written = skipped = 0
    for item in data["utterances"]:
        dest = AUDIO_DIR / f"{item['id']}.wav"
        if dest.exists():
            skipped += 1
            continue
        name = VOICE_FOR_LANG.get(item["language"], "en_US-amy-medium")
        if name not in cache:
            path = VOICE_DIR / f"{name}.onnx"
            if not path.exists():
                print(f"voice {name} missing, run `make models` first")
                return 1
            cache[name] = PiperVoice.load(str(path), config_path=str(path) + ".json")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            cache[name].synthesize_wav(item["text"], wf)
        dest.write_bytes(buf.getvalue())
        written += 1
    print(f"rendered {written} clips, {skipped} already present, into {AUDIO_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
