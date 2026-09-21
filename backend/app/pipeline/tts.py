"""Text to speech.

Three engines behind one call, tried in order and each falling through to the
next rather than going silent mid-demo:

  elevenlabs  only when a key is set. Most natural, and it sends the reply
              text to a third party. A reply can contain a balance or an
              account's last four, so that is customer data leaving the
              machine and every affected turn says so in its trace.
  kokoro      the default. Offline, CPU, real-time factor around 0.35.
  piper       the fallback. Always available once `make models` has run.

Three things this file gets right that the first version did not:

**Gender is one setting.** Piper spoke Hindi with hi_IN-pratham, a male
voice, while Kokoro spoke it with hf_alpha, a female one, so the gender of
the assistant flipped depending on which engine happened to run. There is now
a single BFSI_TTS_GENDER honoured by every engine and language.

**The accent is Indian by default.** For English that means a Hindi Kokoro
voice reading English through the ENGLISH phonemiser. Those are two separate
settings and confusing them is the trap: running English text through the
Hindi phonemiser gives an accent and destroys the words (round-trip WER 0.48
against 0.29).

**It breathes.** Replies are synthesised phrase by phrase and joined with
real pauses, with a little speed variation and an occasional inhale. See
prosody.py. A model handed a whole paragraph reads it at one unbroken pace,
and that is most of what "sounds like AI" means.

The Devanagari rule from before still holds: both offline engines phonemise
from script, so a romanised Hindi reply is read with English vowels.
assert_devanagari refuses to speak one.
"""
from __future__ import annotations

import functools
import io
import os
import re
import wave

import numpy as np

from ..config import (ELEVENLABS_KEY_ENV, ELEVENLABS_MODEL, ELEVENLABS_VOICES,
                      KOKORO_LANG, KOKORO_MODEL, KOKORO_SPEED,
                      KOKORO_VOICE_TABLE, KOKORO_VOICES_BIN, MODEL_DIR,
                      PIPER_LENGTH_SCALE, PIPER_NOISE_SCALE, PIPER_NOISE_W,
                      PIPER_VOICES, SAMPLE_RATE, TTS_ACCENT, TTS_BREATHS,
                      TTS_ENGINE, TTS_GENDER, TTS_NATURAL_PAUSES)
from . import audio_io, prosody
from .speech_text import speak_friendly

VOICE_DIR = MODEL_DIR / "piper"
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def assert_devanagari(text: str, language: str) -> None:
    """Guard against a romanised Hindi or Marathi reply reaching the voice.

    Raises rather than warns, because the failure is silent otherwise: the
    audio plays, it just sounds wrong to anyone who speaks the language.
    """
    if language not in ("hi", "mr"):
        return
    letters = re.sub(r"[^A-Za-zऀ-ॿ]", "", text or "")
    if not letters:
        return
    if not _DEVANAGARI.search(letters):
        raise ValueError(
            f"{language} reply is romanised, not Devanagari: {text[:60]!r}. "
            f"Both offline engines phonemise from script, so this would be read "
            f"with English vowels.")


def _lang(language: str | None) -> str:
    return language if language in ("en", "hi", "mr") else "en"


def kokoro_voice(language: str, gender: str | None = None,
                 accent: str | None = None) -> str:
    table = KOKORO_VOICE_TABLE[_lang(language)]
    return table[(accent or TTS_ACCENT, gender or TTS_GENDER)]


def piper_voice(language: str, gender: str | None = None) -> str:
    return PIPER_VOICES[_lang(language)][gender or TTS_GENDER]


def voice_for(language: str | None) -> str:
    eng = engine()
    lang = _lang(language)
    if eng == "elevenlabs":
        return ELEVENLABS_VOICES[lang]
    return kokoro_voice(lang) if eng == "kokoro" else piper_voice(lang)


def engine() -> str:
    """Which engine a call would actually use right now."""
    if TTS_ENGINE == "piper":
        return "piper"
    if TTS_ENGINE == "elevenlabs":
        return "elevenlabs" if os.environ.get(ELEVENLABS_KEY_ENV) else "kokoro"
    if TTS_ENGINE == "kokoro":
        return "kokoro" if _kokoro() is not None else "piper"
    if os.environ.get(ELEVENLABS_KEY_ENV):
        return "elevenlabs"
    return "kokoro" if _kokoro() is not None else "piper"


@functools.lru_cache(maxsize=1)
def _kokoro():
    if not (KOKORO_MODEL.exists() and KOKORO_VOICES_BIN.exists()):
        return None
    try:
        from kokoro_onnx import Kokoro
        return Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES_BIN))
    except Exception:                                      # noqa: BLE001
        return None


@functools.lru_cache(maxsize=6)
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


def _result(audio: np.ndarray, rate: int, **kw) -> dict:
    return {"audio": _to_wav(audio, rate), "available": True,
            "duration_s": round(len(audio) / rate, 3), "sample_rate": rate,
            "pauses": TTS_NATURAL_PAUSES, "breaths": TTS_BREATHS and TTS_NATURAL_PAUSES,
            "gender": TTS_GENDER, "accent": TTS_ACCENT, **kw}


# ---------------------------------------------------------------- engines

def _speak_kokoro(text: str, lang: str) -> dict | None:
    k = _kokoro()
    if k is None:
        return None
    voice = kokoro_voice(lang)
    phon = KOKORO_LANG[lang]
    speed = KOKORO_SPEED[lang]
    rate = 24000

    def synth(phrase: str, sp: float) -> np.ndarray:
        audio, sr = k.create(phrase, voice=voice, speed=sp, lang=phon)
        return np.asarray(audio, dtype=np.float32)

    try:
        if TTS_NATURAL_PAUSES:
            audio = prosody.speak_with_pauses(text, synth, rate, speed,
                                              breaths=TTS_BREATHS)
        else:
            audio = synth(text, speed)
    except Exception:                                      # noqa: BLE001
        return None
    return _result(audio, rate, voice=voice, language=lang, engine="kokoro",
                   phonemiser=phon, leaves_machine=False,
                   model_id=f"kokoro-82m/{voice}@{phon}")


def _speak_piper(text: str, lang: str) -> dict:
    name = piper_voice(lang)
    try:
        voice = _piper(name)
    except FileNotFoundError as exc:
        return {"audio": b"", "voice": name, "language": lang, "available": False,
                "engine": "none", "error": str(exc), "leaves_machine": False,
                "model_id": f"piper/{name} (missing)"}
    from piper import SynthesisConfig
    rate = voice.config.sample_rate

    def synth(phrase: str, sp: float) -> np.ndarray:
        cfg = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE[lang] / max(sp, 0.1),
                              noise_scale=PIPER_NOISE_SCALE, noise_w_scale=PIPER_NOISE_W)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(phrase, wf, syn_config=cfg)
        return audio_io.decode(buf.getvalue())

    if TTS_NATURAL_PAUSES:
        audio = prosody.speak_with_pauses(text, synth, SAMPLE_RATE, 1.0,
                                          breaths=TTS_BREATHS)
        rate = SAMPLE_RATE
    else:
        audio = synth(text, 1.0)
        rate = SAMPLE_RATE
    return _result(audio, rate, voice=name, language=lang, engine="piper",
                   leaves_machine=False, model_id=f"piper/{name}")


def _speak_elevenlabs(text: str, lang: str) -> dict | None:
    """Most natural of the three, and the only one that sends the reply off
    the machine. A reply can carry a balance, so the trace records it."""
    key = os.environ.get(ELEVENLABS_KEY_ENV)
    if not key:
        return None
    import json
    import urllib.request
    voice = ELEVENLABS_VOICES[lang]
    body = json.dumps({
        "text": text, "model_id": ELEVENLABS_MODEL,
        # ElevenLabs does its own phrasing, so the local pause layer stays off
        # for it and style/stability carry the naturalness instead.
        "voice_settings": {"stability": 0.42, "similarity_boost": 0.8,
                           "style": 0.35, "use_speaker_boost": True},
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_22050_32",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            audio = audio_io.decode(r.read())
    except Exception:                                      # noqa: BLE001
        return None
    return _result(audio, SAMPLE_RATE, voice=voice, language=lang,
                   engine="elevenlabs", leaves_machine=True,
                   model_id=f"elevenlabs/{ELEVENLABS_MODEL}/{voice}")


# ---------------------------------------------------------------- entry point

def synthesize(text: str, language: str | None = None) -> dict:
    """Speak a reply. Never returns silently: a failed engine falls through."""
    lang = _lang(language)
    assert_devanagari(text, lang)
    spoken = speak_friendly(text, lang)
    wanted = engine()

    for name in ("elevenlabs", "kokoro", "piper"):
        if name == "elevenlabs" and wanted != "elevenlabs":
            continue
        if name == "kokoro" and wanted == "piper":
            continue
        out = (_speak_elevenlabs(spoken, lang) if name == "elevenlabs"
               else _speak_kokoro(spoken, lang) if name == "kokoro"
               else _speak_piper(spoken, lang))
        if out is not None:
            if name != wanted:
                out["note"] = f"{wanted} was unavailable, spoke with {name}"
            return out
    return {"audio": b"", "voice": "none", "language": lang, "available": False,
            "engine": "none", "leaves_machine": False,
            "error": "no speech engine available", "model_id": "none"}


def synthesize_array(text: str, language: str | None = None) -> np.ndarray:
    out = synthesize(text, language)
    return audio_io.decode(out["audio"]) if out["audio"] else np.zeros(0, dtype=np.float32)


def model_id() -> str:
    eng = engine()
    if eng == "elevenlabs":
        return f"elevenlabs/{ELEVENLABS_MODEL}"
    return (f"kokoro-82m/{kokoro_voice('en')}" if eng == "kokoro"
            else f"piper/{piper_voice('en')}")
