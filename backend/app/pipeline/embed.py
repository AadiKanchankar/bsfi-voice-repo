"""One sentence-transformer, loaded once, shared by the NLU head and retrieval.

Loading the model twice would double cold start for no benefit, and cold start
under 60 seconds is a hard constraint for the demo.
"""
from __future__ import annotations

import functools
import threading

import numpy as np

from ..config import EMBED_MODEL, MODEL_DIR

_lock = threading.Lock()


LOCAL_DIR = MODEL_DIR / "sentence_transformers" / EMBED_MODEL.split("/")[-1]


@functools.lru_cache(maxsize=1)
def get_model():
    """Prefer the pre-downloaded local copy so a demo launch never touches the
    network. Falls back to the hub only if `make models` was never run."""
    from sentence_transformers import SentenceTransformer
    source = str(LOCAL_DIR) if (LOCAL_DIR / "config.json").exists() else EMBED_MODEL
    return SentenceTransformer(source, device="cpu",
                               cache_folder=str(MODEL_DIR / "sentence_transformers"))


def encode(texts: list[str] | str, normalize: bool = True) -> np.ndarray:
    single = isinstance(texts, str)
    batch = [texts] if single else list(texts)
    with _lock:                      # SentenceTransformer is not thread safe
        vecs = get_model().encode(batch, normalize_embeddings=normalize,
                                  show_progress_bar=False, convert_to_numpy=True)
    return vecs[0] if single else vecs


def model_id() -> str:
    return EMBED_MODEL


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity of a single vector against a matrix of row vectors."""
    a = a / (np.linalg.norm(a) + 1e-12)
    bn = b / (np.linalg.norm(b, axis=-1, keepdims=True) + 1e-12)
    return bn @ a
