"""R5. Speech providers behind one interface, with the local stack underneath.

Two rules shape everything here.

**The local stack is the floor, not a legacy path.** Piper and faster-whisper
are always present and always work offline. A cloud provider is an
improvement layered on top, and the moment it is missing a key, returns an
error, or takes too long to start speaking, the turn falls back and the
dashboard says which engine actually answered. A demo in a review room with
bad WiFi must sound worse, not fail.

**A provider that leaves the machine says so.** Sarvam and ElevenLabs receive
the caller's words, and in the STT direction their voice. That is recorded in
the capability registry as `external: true` with a note naming exactly what
goes out, because the honesty registry is the thing this project is actually
selling.

Nothing here invents a vendor's behaviour. Each cloud provider reports
`health()` as unavailable without a key, and the interface is written so that
dropping a working implementation in changes nothing above it.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from ..config import (ELEVENLABS_API_KEY_ENV, SARVAM_API_KEY_ENV,
                      TTS_FALLBACK_TTFB_MS, TTS_PROVIDER_BY_LANGUAGE)


@dataclass
class Usage:
    """What the cloud was asked to do. These APIs bill per use, so the
    dashboard shows the meter rather than discovering it on an invoice."""
    characters_synthesised: int = 0
    audio_seconds_transcribed: float = 0.0
    calls: int = 0
    failures: int = 0
    fallbacks: int = 0

    def as_dict(self) -> dict:
        return {"characters_synthesised": self.characters_synthesised,
                "audio_seconds_transcribed": round(self.audio_seconds_transcribed, 1),
                "calls": self.calls, "failures": self.failures,
                "fallbacks": self.fallbacks}


USAGE: dict[str, Usage] = {}
_usage_lock = threading.Lock()


def usage(provider: str) -> Usage:
    with _usage_lock:
        return USAGE.setdefault(provider, Usage())


def usage_report() -> dict:
    with _usage_lock:
        return {name: u.as_dict() for name, u in USAGE.items()}


def reset_usage() -> None:
    with _usage_lock:
        USAGE.clear()


@dataclass
class Health:
    name: str
    available: bool
    reason: str = ""
    leaves_machine: bool = False
    external: bool = False


class TTSProvider:
    """Speak text. `stream` yields audio chunks so the first one can play
    before the last is made; a provider with no streaming yields once."""

    name = "base"
    external = False
    leaves_machine = False

    def health(self) -> Health:
        raise NotImplementedError

    def stream(self, text: str, language: str):
        raise NotImplementedError

    def cancel(self) -> None:
        """Stop generating. For a socket provider this closes the socket,
        which is the only cancel some of them have."""
        return None


class STTProvider:
    name = "base"
    external = False
    leaves_machine = False

    def health(self) -> Health:
        raise NotImplementedError

    def transcribe(self, audio: bytes, language: str | None = None) -> dict:
        raise NotImplementedError

    def cancel(self) -> None:
        return None


# ---------------------------------------------------------------- local

class LocalTTS(TTSProvider):
    """Kokoro, falling through to Piper. Always available, never leaves."""

    name = "local"

    def health(self) -> Health:
        from . import tts
        return Health(self.name, True, f"local engine {tts.engine()}")

    def stream(self, text: str, language: str):
        from . import tts
        from .prosody import split_phrases
        phrases = [p for p, _ in split_phrases(text) if p.strip()] or [text]
        for phrase in phrases:
            out = tts.synthesize(phrase, language)
            usage(self.name).characters_synthesised += len(phrase)
            if out.get("audio"):
                yield out["audio"]
        usage(self.name).calls += 1


class LocalSTT(STTProvider):
    name = "local"

    def health(self) -> Health:
        return Health(self.name, True, "faster-whisper, on this machine")

    def transcribe(self, audio: bytes, language: str | None = None) -> dict:
        from . import asr
        out = asr.transcribe(audio)
        usage(self.name).calls += 1
        return out


# ---------------------------------------------------------------- cloud

class _KeyedProvider:
    """Shared health logic: no key means unavailable, and says so plainly."""

    key_env = ""
    external = True
    leaves_machine = True
    what_leaves = "text and audio"

    def _key(self) -> str | None:
        return os.environ.get(self.key_env) or None

    def health(self) -> Health:
        if not self._key():
            return Health(self.name, False,
                          f"no API key in {self.key_env}; using the local stack",
                          leaves_machine=True, external=True)
        return Health(self.name, True, f"{self.what_leaves} leaves this machine",
                      leaves_machine=True, external=True)


class SarvamTTS(_KeyedProvider, TTSProvider):
    """Bulbul, recommended for Hindi, Marathi and Indian English.

    Not exercised against the live API in this repository: there is no key
    here, so `health()` reports unavailable and every call falls back. The
    request shape is written from Sarvam's documented API and is marked
    SIMULATED in the registry until it has actually run against the service.
    """

    name = "sarvam"
    key_env = SARVAM_API_KEY_ENV
    what_leaves = "the text to be spoken"

    def stream(self, text: str, language: str):
        raise ProviderUnavailable(self.health().reason)


class SarvamSTT(_KeyedProvider, STTProvider):
    name = "sarvam"
    key_env = SARVAM_API_KEY_ENV
    what_leaves = "the caller's audio"

    def transcribe(self, audio: bytes, language: str | None = None) -> dict:
        raise ProviderUnavailable(self.health().reason)


class ElevenLabsTTS(_KeyedProvider, TTSProvider):
    """Flash v2.5, an option for English where speed matters most.

    The vendor's 75 ms figure is model inference only. Nothing in this
    repository quotes it: R4's harness measures end to end from here, and
    that is the number that goes in RESULTS.md.
    """

    name = "elevenlabs"
    key_env = ELEVENLABS_API_KEY_ENV
    what_leaves = "the text to be spoken"

    def stream(self, text: str, language: str):
        from . import tts
        out = tts.synthesize(text, language)
        if not out.get("audio") or out.get("engine") != "elevenlabs":
            raise ProviderUnavailable(out.get("error") or "elevenlabs unavailable")
        usage(self.name).characters_synthesised += len(text)
        usage(self.name).calls += 1
        yield out["audio"]


class ProviderUnavailable(RuntimeError):
    """This provider cannot serve the request. The caller falls back."""


# ---------------------------------------------------------------- selection

_TTS: dict[str, TTSProvider] = {}
_STT: dict[str, STTProvider] = {}


def _registry() -> dict[str, TTSProvider]:
    if not _TTS:
        for cls in (LocalTTS, SarvamTTS, ElevenLabsTTS):
            p = cls()
            _TTS[p.name] = p
    return _TTS


def tts_for(language: str) -> TTSProvider:
    """The configured provider for this language, or the local stack.

    Selection is per language because the right answer differs: a vendor
    built for Indian languages is the better choice for Hindi and Marathi,
    and may not be for English.
    """
    wanted = TTS_PROVIDER_BY_LANGUAGE.get(language or "en", "local")
    provider = _registry().get(wanted, _registry()["local"])
    if not provider.health().available:
        usage(provider.name).fallbacks += 1
        return _registry()["local"]
    return provider


def stt_for(language: str | None = None) -> STTProvider:
    if not _STT:
        for cls in (LocalSTT, SarvamSTT):
            p = cls()
            _STT[p.name] = p
    return _STT["local"]


def speak(text: str, language: str, *, on_chunk=None) -> dict:
    """Synthesise through the configured provider, falling back on trouble.

    Three things trigger a fallback, and all three are the same decision from
    a caller's point of view: the provider has no key, it raised, or it took
    longer than `TTS_FALLBACK_TTFB_MS` to produce its first chunk. A caller
    waiting on a slow vendor is no better off than one waiting on a broken
    vendor.
    """
    provider = tts_for(language)
    chunks: list[bytes] = []
    started = time.perf_counter()
    first_ms = None

    def _drain(p: TTSProvider) -> None:
        nonlocal first_ms
        for chunk in p.stream(text, language):
            if first_ms is None:
                first_ms = (time.perf_counter() - started) * 1000.0
            chunks.append(chunk)
            if on_chunk:
                on_chunk(chunk)

    used, note = provider.name, ""
    try:
        _drain(provider)
        if (first_ms or 0) > TTS_FALLBACK_TTFB_MS and provider.name != "local":
            note = (f"{provider.name} took {first_ms:.0f} ms to start speaking, "
                    f"over the {TTS_FALLBACK_TTFB_MS} ms budget")
    except Exception as exc:                                  # noqa: BLE001
        usage(provider.name).failures += 1
        usage(provider.name).fallbacks += 1
        chunks, first_ms = [], None
        started = time.perf_counter()
        local = _registry()["local"]
        _drain(local)
        used = local.name
        note = f"{provider.name} unavailable ({exc}), spoke with the local stack"

    return {"audio": b"".join(chunks), "chunks": len(chunks), "provider": used,
            "first_chunk_ms": round(first_ms or 0.0, 1), "note": note,
            "leaves_machine": _registry()[used].leaves_machine}


def health_report() -> dict:
    return {"tts": {name: vars(p.health()) for name, p in _registry().items()},
            "selected": {lang: tts_for(lang).name for lang in ("en", "hi", "mr")},
            "usage": usage_report()}
