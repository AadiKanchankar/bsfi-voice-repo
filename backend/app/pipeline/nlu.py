"""A3. Intent classification: multilingual sentence embedding + logistic head.

The embedding model is frozen; only the linear head is trained, on the seeded
utterance bank in data/seed/intent_bank.yaml. That keeps training to a couple
of seconds on a laptop, keeps the classifier swappable, and keeps the softmax
posterior meaningful as c_intent for the confidence fusion in A2.

The head is fitted by scripts/seed_data.py and persisted, so a demo cold start
loads a pickle rather than retraining.
"""
from __future__ import annotations

import functools
import pickle
from pathlib import Path

import numpy as np
import yaml

from ..config import INTENTS, RUNTIME_DIR, SEED, SEED_DIR
from . import embed, slots

HEAD_PATH = RUNTIME_DIR / "nlu_head.pkl"
BANK_PATH = SEED_DIR / "intent_bank.yaml"


def load_bank(path: Path | None = None) -> dict[str, list[str]]:
    bank = yaml.safe_load(Path(path or BANK_PATH).read_text(encoding="utf-8"))
    unknown = set(bank) - set(INTENTS)
    if unknown:
        raise ValueError(f"intent_bank.yaml has intents not in config.INTENTS: {unknown}")
    missing = set(INTENTS) - set(bank)
    if missing:
        raise ValueError(f"intent_bank.yaml is missing intents: {missing}")
    return bank


def train(path: Path | None = None, out: Path | None = None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score

    bank = load_bank(path)
    texts, labels = [], []
    for intent, utterances in bank.items():
        texts.extend(utterances)
        labels.extend([intent] * len(utterances))
    X = embed.encode(texts)
    y = np.array(labels)
    clf = LogisticRegression(max_iter=2000, C=8.0, random_state=SEED,
                             class_weight="balanced")
    # Honest number: 5-fold cross validation on the seed set, reported in
    # RESULTS.md as what it is, accuracy on seeded data and not on live audio.
    cv = cross_val_score(clf, X, y, cv=5)
    clf.fit(X, y)
    target = Path(out or HEAD_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as fh:
        pickle.dump({"clf": clf, "embed_model": embed.model_id(),
                     "n_train": len(texts), "cv_accuracy": float(cv.mean()),
                     "cv_std": float(cv.std())}, fh)
    return {"n_train": len(texts), "n_intents": len(bank),
            "cv_accuracy": float(cv.mean()), "cv_std": float(cv.std()),
            "path": str(target)}


@functools.lru_cache(maxsize=1)
def _head() -> dict:
    if not HEAD_PATH.exists():
        raise RuntimeError(
            f"intent head not found at {HEAD_PATH}. Run `make seed` first.")
    with open(HEAD_PATH, "rb") as fh:
        return pickle.load(fh)


def model_id() -> str:
    try:
        h = _head()
        return f"logreg-head/{h['embed_model']}/n={h['n_train']}"
    except RuntimeError:
        return "logreg-head/untrained"


def classify(text: str) -> dict:
    """Returns intent, posterior, and the full ranking for the trace.

    The runner-up matters: a turn where the top two intents are 0.34 and 0.33
    is a turn that should not be automated, and the dashboard shows it.
    """
    head = _head()
    clf = head["clf"]
    vec = embed.encode(text).reshape(1, -1)
    proba = clf.predict_proba(vec)[0]
    order = np.argsort(proba)[::-1]
    ranking = [{"intent": str(clf.classes_[i]), "p": round(float(proba[i]), 4)}
               for i in order[:5]]
    return {"intent": str(clf.classes_[order[0]]),
            "confidence": float(proba[order[0]]),
            "margin": float(proba[order[0]] - proba[order[1]]) if len(order) > 1 else 1.0,
            "ranking": ranking,
            "model_id": model_id()}


def understand(text: str) -> dict:
    """Intent plus slots. One call, one record in the trace."""
    out = classify(text)
    out["slots"] = slots.extract(text, out["intent"])
    return out
