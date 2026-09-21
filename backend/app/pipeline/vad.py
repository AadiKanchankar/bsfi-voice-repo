"""Silero VAD endpointing. Trims leading and trailing silence before ASR so
the model is not asked to transcribe room tone, and reports how much audio it
dropped so the trace shows it.

Falls back to an energy gate if the Silero model is not present, and says so in
the stage notes rather than pretending the neural VAD ran.
"""
from __future__ import annotations

import functools

import numpy as np

from ..config import SAMPLE_RATE, VAD_MIN_SILENCE_MS, VAD_MIN_SPEECH_MS, VAD_THRESHOLD
from . import audio_io


@functools.lru_cache(maxsize=1)
def _silero():
    from silero_vad import get_speech_timestamps, load_silero_vad
    return load_silero_vad(onnx=True), get_speech_timestamps


def trim_to_speech(data: bytes | np.ndarray) -> dict:
    audio = audio_io.decode(data) if isinstance(data, (bytes, bytearray)) else data
    total = audio_io.duration_s(audio)
    try:
        model, get_ts = _silero()
        import torch
        ts = get_ts(torch.from_numpy(audio), model, sampling_rate=SAMPLE_RATE,
                    threshold=VAD_THRESHOLD, min_silence_duration_ms=VAD_MIN_SILENCE_MS,
                    min_speech_duration_ms=VAD_MIN_SPEECH_MS)
        model_id, method = "silero-vad-v6-onnx", "neural"
    except Exception as exc:                       # noqa: BLE001
        ts, model_id, method = _energy_gate(audio), f"energy-gate (silero unavailable: {exc})", "energy"

    if not ts:
        return {"audio": audio, "model_id": model_id,
                "summary": {"speech_segments": 0, "total_s": round(total, 3),
                            "speech_s": 0.0, "method": method,
                            "note": "no speech detected, passing the full buffer to ASR"}}
    start, end = ts[0]["start"], ts[-1]["end"]
    trimmed = audio[start:end]
    speech_s = sum((t["end"] - t["start"]) for t in ts) / SAMPLE_RATE
    return {"audio": trimmed, "model_id": model_id,
            "summary": {"speech_segments": len(ts), "total_s": round(total, 3),
                        "speech_s": round(speech_s, 3),
                        "trimmed_s": round(total - audio_io.duration_s(trimmed), 3),
                        "method": method, "threshold": VAD_THRESHOLD}}


def _energy_gate(audio: np.ndarray, frame_ms: int = 30) -> list[dict]:
    n = int(SAMPLE_RATE * frame_ms / 1000)
    if len(audio) < n:
        return []
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    energy = np.sqrt((frames ** 2).mean(axis=1))
    thr = max(float(energy.mean()) * 0.5, 1e-3)
    voiced = energy > thr
    segments, start = [], None
    for i, v in enumerate(voiced):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segments.append({"start": start * n, "end": i * n})
            start = None
    if start is not None:
        segments.append({"start": start * n, "end": len(voiced) * n})
    return segments
