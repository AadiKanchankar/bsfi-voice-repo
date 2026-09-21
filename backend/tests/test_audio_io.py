"""Audio decoding. The browser does not send WAV.

MediaRecorder in Chrome produces WebM with Opus. A decoder that only reads
WAV passes every test written with synthesised WAV fixtures and then fails on
every microphone turn in the live demo, which is exactly what happened here.
"""
import io

import numpy as np
import pytest

from app.config import SAMPLE_RATE
from app.pipeline import audio_io


@pytest.fixture()
def tone():
    t = np.linspace(0, 1.0, SAMPLE_RATE, endpoint=False)
    return (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def encode(audio: np.ndarray, fmt: str, codec: str) -> bytes:
    import av
    buf = io.BytesIO()
    with av.open(buf, mode="w", format=fmt) as out:
        stream = out.add_stream(codec, rate=48000)
        stream.layout = "mono"
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=48000)
        frame = av.AudioFrame.from_ndarray(
            (audio * 32767).astype("int16").reshape(1, -1), format="s16", layout="mono")
        frame.rate = SAMPLE_RATE
        for f in resampler.resample(frame):
            for packet in stream.encode(f):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


def test_wav_round_trip(tone):
    back = audio_io.decode(audio_io.to_wav_bytes(tone))
    assert len(back) == len(tone)
    assert np.max(np.abs(back - tone)) < 1e-3


@pytest.mark.parametrize("fmt,codec", [("webm", "libopus"), ("ogg", "libopus"),
                                       ("mp4", "aac")])
def test_browser_containers_decode(tone, fmt, codec):
    data = encode(tone, fmt, codec)
    assert not data.startswith(b"RIFF")
    back = audio_io.decode(data)
    # Lossy codecs and the resampler shift the length slightly.
    assert 0.9 < len(back) / len(tone) < 1.15, len(back)
    assert float(np.sqrt((back ** 2).mean())) > 0.05, "decoded to silence"


def test_raw_pcm_still_works(tone):
    pcm = (tone * 32767).astype(np.int16).tobytes()
    back = audio_io.decode(pcm)
    assert len(back) == len(tone)


def test_empty_input_is_empty_not_an_exception():
    assert len(audio_io.decode(b"")) == 0


def test_resampling_changes_length_proportionally(tone):
    out = audio_io.resample(tone, SAMPLE_RATE, 8000)
    assert abs(len(out) - len(tone) // 2) <= 1
