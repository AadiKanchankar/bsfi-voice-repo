"""Text to speech, offline and CPU only.

Two engines behind one interface:

  kokoro  Kokoro-82M ONNX, the default. Markedly more natural than Piper and
          fast enough on CPU (real-time factor around 0.4 measured on the
          development laptop). Handles Devanagari directly with a Hindi voice.
  piper   The fallback, used automatically when the Kokoro model is not
          present or fails to load, and forced by BFSI_TTS_ENGINE=piper.

Voice is chosen from the dominant language span of the turn, so a Hindi
question gets a Hindi answer without anybody setting a flag.

The Devanagari rule is not cosmetic. Both engines phonemise from script, so a
romanised Hindi reply is read with English vowels: "khatam hone wale" comes
out as "kɑːtam həʊn weɪl" instead of "kʰʌtmə hoːneː ʋaːleː". Every reply
template in banking/actions.py is therefore written in Devanagari, and
assert_devanagari below is what stops a romanised one creeping back in.

There is no Marathi voice in either engine. Marathi is spoken with the Hindi
voice, which is phonetically close for Devanagari text and far better than the
romanised alternative, and the capability registry says so.
"""
from __future__ import annotations

import functools
import io
import re
import wave

import numpy as np

from ..config import (KOKORO_LANG, KOKORO_MODEL, KOKORO_SPEED, KOKORO_VOICES,
                      KOKORO_VOICES_BIN, MODEL_DIR, PIPER_LENGTH_SCALE,
                      PIPER_NOISE_SCALE, PIPER_NOISE_W, PIPER_VOICES,
                      SAMPLE_RATE, TTS_ENGINE)
from . import audio_io
from .speech_text import speak_friendly

VOICE_DIR = MODEL_DIR / "piper"

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def assert_devanagari(text: str, language: str) -> None:
    """Guard against a romanised Hindi or Marathi reply reaching the voice.

    Raises rather than warns, because the failure is silent otherwise: the
    audio still plays, it just sounds wrong to anyone who speaks the language,
    which is how this shipped in the first place.
    """
    if language not in ("hi", "mr"):
        return
    letters = re.sub(r"[^A-Za-zऀ-ॿ]", "", text or "")
    if not letters:
        return
    if not _DEVANAGARI.search(letters):
        raise ValueError(
            f"{language} reply is romanised, not Devanagari: {text[:60]!r}. "
            f"Both engines phonemise from script, so this would be read with "
            f"English vowels.")


def voice_for(language: str | None) -> str:
    if engine() == "kokoro":
        return KOKORO_VOICES.get(language or "en", KOKORO_VOICES["en"])
    return PIPER_VOICES.get(language or "en", PIPER_VOICES["en"])


def engine() -> str:
    if TTS_ENGINE == "piper":
        return "piper"
    return "kokoro" if _kokoro() is not None else "piper"


@functools.lru_cache(maxsize=1)
def _kokoro():
    if not (KOKORO_MODEL.exists() and KOKORO_VOICES_BIN.exists()):
        return None
    try:
        from kokoro_onnx import Kokoro
        return Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES_BIN))
    except Exception:                                  # noqa: BLE001
        return None


@functools.lru_cache(maxsize=4)
def _piper(name: str):
    from piper import PiperVoice
    path = VOICE_DIR / f"{name}.onnx"
    if not path.exists():
        raise FileNotFoundError(f"Piper voice {name} is not downloaded. Run `make models`.")
    return PiperVoice.load(str(path), config_path=str(path) + ".json")


def _to_wav(audio: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def synthesize(text: str, language: str | None = None) -> dict:
    """Returns WAV bytes plus the metadata the trace records.

    A missing voice is reported, not hidden. A demo that silently returns no
    audio is worse than one that says the voice is not installed.
    """
    lang = language if language in ("en", "hi", "mr") else "en"
    assert_devanagari(text, lang)
    spoken = speak_friendly(text, lang)

    k = None if TTS_ENGINE == "piper" else _kokoro()
    if k is not None:
        try:
            audio, rate = k.create(spoken, voice=KOKORO_VOICES[lang],
                                   speed=KOKORO_SPEED[lang], lang=KOKORO_LANG[lang])
            audio = np.asarray(audio, dtype=np.float32)
            return {"audio": _to_wav(audio, rate), "voice": KOKORO_VOICES[lang],
                    "language": lang, "available": True, "engine": "kokoro",
                    "duration_s": round(len(audio) / rate, 3),
                    "model_id": f"kokoro-82m/{KOKORO_VOICES[lang]}"}
        except Exception as exc:                        # noqa: BLE001
            # Fall through to Piper rather than going silent mid-demo.
            fallback_note = f"kokoro failed ({exc}), fell back to piper"
    else:
        fallback_note = None

    name = PIPER_VOICES[lang]
    try:
        voice = _piper(name)
    except FileNotFoundError as exc:
        return {"audio": b"", "voice": name, "language": lang, "available": False,
                "engine": "none", "error": str(exc), "model_id": f"piper/{name} (missing)"}
    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE[lang],
                          noise_scale=PIPER_NOISE_SCALE, noise_w_scale=PIPER_NOISE_W)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(spoken, wf, syn_config=cfg)
    data = buf.getvalue()
    out = {"audio": data, "voice": name, "language": lang, "available": True,
           "engine": "piper", "duration_s": round(len(audio_io.decode(data)) / SAMPLE_RATE, 3),
           "model_id": f"piper/{name}"}
    if fallback_note:
        out["note"] = fallback_note
    return out


def synthesize_array(text: str, language: str | None = None) -> np.ndarray:
    out = synthesize(text, language)
    return audio_io.decode(out["audio"]) if out["audio"] else np.zeros(0, dtype=np.float32)


def model_id() -> str:
    lang = "en"
    return (f"kokoro-82m/{KOKORO_VOICES[lang]}" if engine() == "kokoro"
            else f"piper/{PIPER_VOICES[lang]}")
