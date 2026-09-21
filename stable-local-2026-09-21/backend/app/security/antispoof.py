"""A6, second half. Anti-spoofing, registered as BASELINE and labelled that way
on screen.

A trained AASIST countermeasure is out of scope for this demo and claiming one
would not survive a review question. What is here instead is a real, classical,
defensible baseline: linear frequency cepstral coefficients with delta and
double delta features, and a two class Gaussian mixture model scored as a log
likelihood ratio.

    llr   = log p(x | bona fide) - log p(x | spoof)
    score = sigmoid(llr / s)      mapped to (0, 1)

The score multiplies the speaker cosine to give s_verify, exactly as the
synopsis specifies, so a suspected spoof drags verification down and pushes the
risk score up rather than being a separate yes or no gate.

The interface is the point of the exercise:

    AntiSpoofScorer.score(audio) -> float in [0, 1], 1 means bona fide

Drop a trained AASIST behind that signature and nothing above this file
changes.
"""
from __future__ import annotations

import functools
import pickle
from pathlib import Path

import numpy as np
from scipy.fftpack import dct

from ..config import (ANTISPOOF_GMM_COMPONENTS, ANTISPOOF_LFCC_FILTERS, RUNTIME_DIR,
                      SAMPLE_RATE, SEED)
from ..pipeline import audio_io

MODEL_PATH = RUNTIME_DIR / "antispoof_gmm.pkl"
LLR_SCALE = 2.0           # slope of the sigmoid that maps the LLR into (0, 1)


# ---------------------------------------------------------------- features

def _linear_filterbank(n_filters: int, n_fft: int, sr: int) -> np.ndarray:
    """Triangular filters spaced linearly in Hz.

    Linear, not mel. Mel spacing throws away the high frequency detail where
    vocoder artefacts live, which is precisely the evidence a countermeasure
    needs.
    """
    edges = np.linspace(0, sr / 2, n_filters + 2)
    bins = np.floor((n_fft + 1) * edges / sr).astype(int)
    fb = np.zeros((n_filters, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_filters + 1):
        left, centre, right = bins[m - 1], bins[m], bins[m + 1]
        if centre == left:
            centre = left + 1
        if right == centre:
            right = centre + 1
        right = min(right, fb.shape[1] - 1)
        centre = min(centre, right - 1) if right - 1 > left else centre
        for k in range(left, centre):
            fb[m - 1, k] = (k - left) / max(centre - left, 1)
        for k in range(centre, right):
            fb[m - 1, k] = (right - k) / max(right - centre, 1)
    return fb


def _deltas(feat: np.ndarray, width: int = 2) -> np.ndarray:
    if len(feat) < 3:
        return np.zeros_like(feat)
    padded = np.pad(feat, ((width, width), (0, 0)), mode="edge")
    denom = 2 * sum(i * i for i in range(1, width + 1))
    out = np.zeros_like(feat)
    for t in range(len(feat)):
        acc = np.zeros(feat.shape[1])
        for i in range(1, width + 1):
            acc += i * (padded[t + width + i] - padded[t + width - i])
        out[t] = acc / denom
    return out


def lfcc(data: bytes | np.ndarray, n_filters: int = ANTISPOOF_LFCC_FILTERS,
         n_ceps: int = 20, frame_ms: int = 25, hop_ms: int = 10) -> np.ndarray:
    """LFCC with deltas and double deltas. Returns (frames, 3 * n_ceps)."""
    audio = audio_io.decode(data) if isinstance(data, (bytes, bytearray)) else data
    n_fft = int(SAMPLE_RATE * frame_ms / 1000)
    hop = int(SAMPLE_RATE * hop_ms / 1000)
    if len(audio) < n_fft:
        audio = np.pad(audio, (0, n_fft - len(audio)))
    window = np.hamming(n_fft).astype(np.float32)
    n_frames = 1 + (len(audio) - n_fft) // hop
    frames = np.lib.stride_tricks.as_strided(
        audio, shape=(n_frames, n_fft),
        strides=(audio.strides[0] * hop, audio.strides[0])).copy()
    spec = np.abs(np.fft.rfft(frames * window, n=n_fft)) ** 2
    fb = _linear_filterbank(n_filters, n_fft, SAMPLE_RATE)
    energies = np.log(spec @ fb.T + 1e-10)
    ceps = dct(energies, type=2, axis=1, norm="ortho")[:, :n_ceps]
    return np.hstack([ceps, _deltas(ceps), _deltas(_deltas(ceps))]).astype(np.float32)


# ---------------------------------------------------------------- model

class AntiSpoofScorer:
    """The swappable interface. score(audio) -> float in [0, 1]."""

    capability = "BASELINE"

    def score(self, audio: bytes | np.ndarray) -> float:
        raise NotImplementedError


class LfccGmmScorer(AntiSpoofScorer):
    def __init__(self, bona, spoof, mu, sigma):
        self.bona, self.spoof, self.mu, self.sigma = bona, spoof, mu, sigma

    def _norm(self, feats: np.ndarray) -> np.ndarray:
        return (feats - self.mu) / (self.sigma + 1e-8)

    def llr(self, audio: bytes | np.ndarray) -> float:
        feats = self._norm(lfcc(audio))
        return float(self.bona.score(feats) - self.spoof.score(feats))

    def score(self, audio: bytes | np.ndarray) -> float:
        return float(1.0 / (1.0 + np.exp(-self.llr(audio) / LLR_SCALE)))


def train(bona_clips: list, spoof_clips: list, out: Path | None = None) -> dict:
    from sklearn.mixture import GaussianMixture
    bona_feats = np.vstack([lfcc(c) for c in bona_clips])
    spoof_feats = np.vstack([lfcc(c) for c in spoof_clips])
    allf = np.vstack([bona_feats, spoof_feats])
    mu, sigma = allf.mean(axis=0), allf.std(axis=0)
    n_comp = min(ANTISPOOF_GMM_COMPONENTS,
                 max(1, min(len(bona_feats), len(spoof_feats)) // 20))
    kwargs = dict(n_components=n_comp, covariance_type="diag", random_state=SEED,
                  reg_covar=1e-4, max_iter=200)
    bona = GaussianMixture(**kwargs).fit((bona_feats - mu) / (sigma + 1e-8))
    spoof = GaussianMixture(**kwargs).fit((spoof_feats - mu) / (sigma + 1e-8))
    target = Path(out or MODEL_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as fh:
        pickle.dump({"bona": bona, "spoof": spoof, "mu": mu, "sigma": sigma,
                     "n_components": n_comp, "n_bona": len(bona_clips),
                     "n_spoof": len(spoof_clips)}, fh)
    return {"n_components": n_comp, "n_bona_clips": len(bona_clips),
            "n_spoof_clips": len(spoof_clips), "feature_dim": int(allf.shape[1]),
            "path": str(target)}


@functools.lru_cache(maxsize=1)
def _scorer() -> LfccGmmScorer | None:
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as fh:
        d = pickle.load(fh)
    return LfccGmmScorer(d["bona"], d["spoof"], d["mu"], d["sigma"])


def model_id() -> str:
    return "LFCC+GMM baseline (BASELINE, not AASIST)"


def score(audio: bytes | np.ndarray) -> dict:
    """Returns the score plus everything the dashboard needs to explain it.

    When no countermeasure has been trained the score is 1.0 and the record
    says untrained. Returning a confident 1.0 without saying so would be the
    exact kind of quiet overclaim this project exists to avoid.
    """
    scorer = _scorer()
    if scorer is None:
        return {"score": 1.0, "llr": None, "bona_fide": True,
                "model_id": model_id(), "trained": False,
                "note": "no countermeasure trained; run `make seed` to fit the baseline"}
    llr = scorer.llr(audio)
    s = float(1.0 / (1.0 + np.exp(-llr / LLR_SCALE)))
    return {"score": round(s, 4), "llr": round(llr, 4), "bona_fide": s >= 0.5,
            "model_id": model_id(), "trained": True,
            "note": "classical baseline, feeds s_verify = s_cos * spoof_score"}
