"""A6, first half. ECAPA-TDNN speaker verification.

Enrolment is the mean of the L2-normalised embeddings of three utterances.
Verification is cosine similarity against that mean, accepted above theta.

theta is not asserted. It is set at the Equal Error Rate measured on the
synthetic trial set by `make eval`, written to runtime/calibration.json, and
reported in RESULTS.md as a measured number with the trial count next to it.
Until that runs, the config default is used and the trace says so.
"""
from __future__ import annotations

import functools
import sqlite3
from pathlib import Path

import numpy as np

from ..config import DATA_DIR, MODEL_DIR, SAMPLE_RATE, SPEAKER_MODEL, SPEAKER_THETA
from ..trace import utcnow
from ..pipeline import audio_io


@functools.lru_cache(maxsize=1)
def _encoder():
    from speechbrain.inference.speaker import EncoderClassifier
    return EncoderClassifier.from_hparams(
        source=SPEAKER_MODEL, savedir=str(MODEL_DIR / "ecapa"),
        run_opts={"device": "cpu"})


def model_id() -> str:
    return f"{SPEAKER_MODEL}@cosine"


def embed_audio(data: bytes | np.ndarray) -> np.ndarray:
    import torch
    audio = audio_io.decode(data) if isinstance(data, (bytes, bytearray)) else data
    if len(audio) < SAMPLE_RATE // 4:                 # pad very short clips
        audio = np.pad(audio, (0, SAMPLE_RATE // 4 - len(audio)))
    with torch.no_grad():
        emb = _encoder().encode_batch(torch.from_numpy(audio).unsqueeze(0))
    v = emb.squeeze().cpu().numpy().astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


def enrol(conn: sqlite3.Connection, customer_id: str, clips: list[bytes | np.ndarray],
          source: str = "synthetic") -> dict:
    if len(clips) < 3:
        raise ValueError("enrolment needs three utterances")
    embeddings = np.stack([embed_audio(c) for c in clips])
    mean = embeddings.mean(axis=0)
    mean = mean / (np.linalg.norm(mean) + 1e-12)
    conn.execute(
        "INSERT OR REPLACE INTO speakers (customer_id, embedding, n_clips, source, enrolled_at)"
        " VALUES (?,?,?,?,?)",
        (customer_id, mean.astype(np.float32).tobytes(), len(clips), source,
         utcnow().isoformat()))
    conn.commit()
    # Self-consistency of the enrolment clips, reported so a bad enrolment is
    # visible at enrolment time rather than at verification time.
    pairwise = [float(embeddings[i] @ embeddings[j])
                for i in range(len(embeddings)) for j in range(i + 1, len(embeddings))]
    return {"customer_id": customer_id, "n_clips": len(clips), "source": source,
            "mean_pairwise_cosine": round(float(np.mean(pairwise)), 4),
            "model_id": model_id()}


def get_enrolment(conn: sqlite3.Connection, customer_id: str) -> tuple[np.ndarray, str] | None:
    row = conn.execute("SELECT embedding, source FROM speakers WHERE customer_id=?",
                       (customer_id,)).fetchone()
    if not row:
        return None
    return np.frombuffer(row["embedding"], dtype=np.float32), row["source"]


def verify(conn: sqlite3.Connection, customer_id: str,
           trial: bytes | np.ndarray) -> dict:
    from ..config import SPEAKER_THETA as theta_now       # picks up calibration
    enrolled = get_enrolment(conn, customer_id)
    if enrolled is None:
        return {"score": 0.0, "threshold": theta_now, "passed": False,
                "reason": "no enrolment on file", "model_id": model_id(),
                "source": None}
    ref, source = enrolled
    x = embed_audio(trial)
    score = float(ref @ x)                    # both L2-normalised
    return {"score": score, "threshold": float(theta_now),
            "passed": score >= theta_now, "model_id": model_id(),
            "source": source,
            "reason": "cosine against the enrolment mean"}


def load_clip(name: str) -> bytes:
    """Load a seeded voice clip by name, for the text-fallback demo path."""
    path = Path(name)
    if not path.is_absolute():
        path = DATA_DIR / "seed" / "voices" / name
    return path.read_bytes()


def eer(target_scores: np.ndarray, nontarget_scores: np.ndarray) -> tuple[float, float]:
    """Equal Error Rate and the threshold at which it occurs.

    Swept over every distinct score in the pooled set, so the reported number
    is the real crossing point and not an interpolation between coarse bins.
    """
    thresholds = np.unique(np.concatenate([target_scores, nontarget_scores]))
    if len(thresholds) == 0:
        return 1.0, 0.0
    best_gap, best_eer, best_t = 2.0, 1.0, float(thresholds[0])
    for t in thresholds:
        frr = float(np.mean(target_scores < t)) if len(target_scores) else 0.0
        far = float(np.mean(nontarget_scores >= t)) if len(nontarget_scores) else 0.0
        gap = abs(frr - far)
        if gap < best_gap:
            best_gap, best_eer, best_t = gap, (frr + far) / 2.0, float(t)
    return best_eer, best_t
