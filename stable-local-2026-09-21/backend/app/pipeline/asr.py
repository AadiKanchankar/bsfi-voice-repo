"""faster-whisper on CPU, int8.

Not fine-tuned on banking audio. The capability registry says so and RESULTS.md
says so. The entity-level error rate measured against this model is the
baseline a fine-tuned model has to beat, and framing it that way is a stronger
result than claiming a number we did not earn.

IndicConformer stays behind a flag for machines with a GPU; it is not on the
demo path and is reported separately if it is ever run.
"""
from __future__ import annotations

import functools
import math

import numpy as np

from ..config import (ASR_COMPUTE_TYPE, ASR_DEVICE, ASR_MODEL_SIZE, MODEL_DIR,
                      USE_INDIC_CONFORMER)
from . import audio_io


@functools.lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    return WhisperModel(ASR_MODEL_SIZE, device=ASR_DEVICE, compute_type=ASR_COMPUTE_TYPE,
                        download_root=str(MODEL_DIR / "faster-whisper"))


def model_id() -> str:
    if USE_INDIC_CONFORMER:
        return "ai4bharat/indic-conformer (GPU flag)"
    return f"faster-whisper/{ASR_MODEL_SIZE}/{ASR_COMPUTE_TYPE}"


def transcribe(data: bytes | np.ndarray, language: str | None = None) -> dict:
    """Returns text plus an honest confidence.

    Whisper does not emit a calibrated confidence, so we map the mean segment
    log probability through exp() and say in the trace that it is a proxy. A
    made-up confidence would poison the fusion in A2 and every risk score after
    it.
    """
    audio = audio_io.decode(data) if isinstance(data, (bytes, bytearray)) else data
    segments, info = _model().transcribe(
        audio, language=language, beam_size=5, vad_filter=False,
        word_timestamps=False, condition_on_previous_text=False)
    segs = list(segments)
    text = " ".join(s.text.strip() for s in segs).strip()
    if segs:
        weights = [max(s.end - s.start, 1e-3) for s in segs]
        avg_lp = sum(s.avg_logprob * w for s, w in zip(segs, weights)) / sum(weights)
    else:
        avg_lp = -5.0
    return {"text": text, "n_segments": len(segs),
            "language": info.language, "language_probability": info.language_probability,
            "avg_logprob": round(float(avg_lp), 4),
            "confidence": round(float(min(1.0, math.exp(avg_lp))), 4),
            "duration_s": round(audio_io.duration_s(audio), 3),
            "model_id": model_id()}
