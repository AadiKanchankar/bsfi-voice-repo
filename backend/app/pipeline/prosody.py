"""Making synthesised speech breathe.

A neural voice handed a whole paragraph reads it at one unbroken pace. People
do not: they group words into phrases, pause at the joints, pause longer at a
full stop, and take a breath before a long run. The absence of that is most of
what "sounds like AI" means, more than the timbre does.

Three things here, in order of how much they matter:

  chunking   synthesise phrase by phrase and join with real silence, rather
             than hoping the model inserts its own pauses
  variation  a few percent of speed jitter per phrase, because a perfectly
             constant rate is the giveaway
  breath     a quiet procedural inhale before a long sentence

None of this touches the words. The transcript stored in the trace is the
text; this only changes how it is spoken.
"""
from __future__ import annotations

import random
import re

import numpy as np

# Pause lengths, seconds. Tuned by ear against the demo replies; a bank
# assistant should sound unhurried rather than brisk.
PAUSE_SENTENCE = 0.34
PAUSE_CLAUSE = 0.16
PAUSE_LIST = 0.11
SPEED_JITTER = 0.03          # +/- 3 percent per phrase
BREATH_BEFORE_WORDS = 14     # inhale before a phrase at least this long
BREATH_GAIN = 0.035
BREATH_MS = 220

# Split after sentence enders and at clause joints, keeping the delimiter.
# The Devanagari danda counts as a full stop.
_SPLIT = re.compile(r"(?<=[.!?।])\s+|(?<=[,;:])\s+")


def split_phrases(text: str) -> list[tuple[str, float]]:
    """Text to (phrase, pause after it in seconds)."""
    out: list[tuple[str, float]] = []
    for part in _SPLIT.split((text or "").strip()):
        part = part.strip()
        if not part:
            continue
        if part[-1] in ".!?।":
            pause = PAUSE_SENTENCE
        elif part[-1] in ";:":
            pause = PAUSE_CLAUSE
        elif part[-1] == ",":
            pause = PAUSE_LIST
        else:
            pause = PAUSE_CLAUSE
        out.append((part, pause))
    if out:
        out[-1] = (out[-1][0], 0.0)          # nothing to pause for at the end
    return out


def breath(rate: int, rng: random.Random) -> np.ndarray:
    """A procedural inhale: band-limited noise under a soft envelope.

    Not a recording. It is quiet enough to read as breath rather than as
    noise, and it only appears before long phrases, which is roughly where a
    person would take one.
    """
    n = int(rate * BREATH_MS / 1000)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    noise = np.array([rng.gauss(0, 1) for _ in range(n)], dtype=np.float32)
    # Cheap band pass: difference removes rumble, running mean removes hiss.
    noise = np.diff(noise, prepend=noise[0])
    k = max(2, rate // 4000)
    noise = np.convolve(noise, np.ones(k, dtype=np.float32) / k, mode="same")
    # Slow in, slower out: an inhale swells rather than clicks.
    t = np.linspace(0, 1, n, dtype=np.float32)
    # Clipped before the power: in float32, sin(pi) lands a hair below zero
    # and a negative base with a fractional exponent is NaN.
    envelope = np.clip(np.sin(np.pi * t), 0.0, None) ** 1.6
    out = noise * envelope
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * BREATH_GAIN).astype(np.float32)


def silence(seconds: float, rate: int) -> np.ndarray:
    return np.zeros(max(0, int(seconds * rate)), dtype=np.float32)


def assemble(pieces: list[np.ndarray], rate: int) -> np.ndarray:
    parts = [p for p in pieces if p is not None and len(p)]
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32)


def speak_with_pauses(text: str, synth, rate: int, base_speed: float = 1.0,
                      breaths: bool = True, seed: int = 0) -> np.ndarray:
    """Synthesise phrase by phrase and join with pauses.

    `synth(phrase, speed) -> np.ndarray` does the actual generation, so this
    works with any engine. Deterministic for a given seed, which keeps the
    tests reproducible.
    """
    rng = random.Random(seed or (abs(hash(text)) % (2 ** 31)))
    phrases = split_phrases(text)
    if not phrases:
        return np.zeros(0, dtype=np.float32)

    pieces: list[np.ndarray] = []
    for i, (phrase, pause) in enumerate(phrases):
        if breaths and i > 0 and len(phrase.split()) >= BREATH_BEFORE_WORDS:
            pieces.append(breath(rate, rng))
        speed = base_speed * (1.0 + rng.uniform(-SPEED_JITTER, SPEED_JITTER))
        audio = synth(phrase, speed)
        if audio is not None and len(audio):
            pieces.append(np.asarray(audio, dtype=np.float32))
        if pause:
            pieces.append(silence(pause, rate))
    return assemble(pieces, rate)


def demo() -> None:
    p = split_phrases("Your balance is fifty thousand rupees. Anything else, or shall I "
                      "close the call?")
    assert len(p) == 3, p
    assert p[0][1] == PAUSE_SENTENCE and p[1][1] == PAUSE_LIST and p[2][1] == 0.0
    assert split_phrases("आपके खाते में पैसे हैं। और कुछ?")[0][1] == PAUSE_SENTENCE
    b = breath(24000, random.Random(1))
    assert 0 < float(np.max(np.abs(b))) <= BREATH_GAIN + 1e-6
    assert len(b) == int(24000 * BREATH_MS / 1000)
    out = speak_with_pauses("One. Two.", lambda t, s: np.ones(100, dtype=np.float32),
                            rate=100, seed=1)
    assert len(out) == 100 + int(PAUSE_SENTENCE * 100) + 100
    print("prosody ok:", [(t[:22], t2) for t, t2 in p])
