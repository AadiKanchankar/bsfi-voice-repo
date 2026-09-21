"""Audio helpers shared by VAD, ASR, speaker verification and anti-spoofing.

Everything downstream expects float32 mono at 16 kHz in memory. Nothing here
writes a file: raw audio must never reach disk, and tests/test_no_raw_audio.py
asserts that after a turn.
"""
from __future__ import annotations

import io
import wave

import numpy as np

from ..config import SAMPLE_RATE


def decode(data: bytes) -> np.ndarray:
    """Bytes to float32 mono at SAMPLE_RATE.

    Handles WAV directly, anything else through PyAV, and raw int16 PCM as the
    last resort. The PyAV branch is not optional: the browser's MediaRecorder
    produces WebM with Opus, so without it every microphone turn from the
    customer console fails while the WAV-based tests all pass.
    """
    if not data:
        return np.zeros(0, dtype=np.float32)
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as wf:
            sr, ch, width = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
        audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        audio = audio / float(np.iinfo(dtype).max) if width > 1 else (audio - 128) / 128.0
        if ch > 1:
            audio = audio.reshape(-1, ch).mean(axis=1)
    elif _is_container(data):
        return _decode_container(data)
    else:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        sr = SAMPLE_RATE
    if sr != SAMPLE_RATE:
        audio = resample(audio, sr, SAMPLE_RATE)
    return np.ascontiguousarray(audio, dtype=np.float32)


# Magic bytes for the containers a browser or a phone might send.
_CONTAINER_MAGIC = (
    b"\x1a\x45\xdf\xa3",   # Matroska and WebM, which is what MediaRecorder emits
    b"OggS",               # Ogg, Opus or Vorbis
    b"fLaC",
    b"ID3",
)


def _is_container(data: bytes) -> bool:
    if any(data.startswith(m) for m in _CONTAINER_MAGIC):
        return True
    # MP4 and M4A put a size field before the ftyp box.
    return len(data) > 12 and data[4:8] == b"ftyp"


def _decode_container(data: bytes) -> np.ndarray:
    """Decode a compressed container with PyAV, resampling to mono 16 kHz.

    PyAV ships with faster-whisper, so this adds no dependency.
    """
    import av

    with av.open(io.BytesIO(data)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=SAMPLE_RATE)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):        # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    pcm = np.concatenate(chunks).astype(np.float32) / 32768.0
    return np.ascontiguousarray(pcm, dtype=np.float32)


def resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return audio
    n = int(round(len(audio) * dst / src))
    return np.interp(np.linspace(0, len(audio), n, endpoint=False),
                     np.arange(len(audio)), audio).astype(np.float32)


def to_wav_bytes(audio: np.ndarray, sr: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def duration_s(audio: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    return len(audio) / sr
