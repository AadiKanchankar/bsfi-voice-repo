"""A9. Evaluation metrics, all computed here rather than imported.

The Levenshtein alignment is written out rather than pulled from a library
because the entity-level error rate needs the alignment itself, not just the
distance. That metric is the headline evaluation claim of the paper: a
transcript that is 95 percent correct but wrong on the amount is worse than
useless in banking, so accuracy on financial entities is reported separately
from headline WER and reported even when it looks bad.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

import numpy as np

Op = Literal["match", "sub", "del", "ins"]


def normalize_tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = re.sub(r"[^\w\sऀ-ॿ]", " ", t)
    return t.split()


@dataclass
class Alignment:
    ops: list[tuple[Op, int | None, int | None]]     # (op, ref index, hyp index)
    substitutions: int
    deletions: int
    insertions: int
    matches: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    def ref_to_hyp(self) -> dict[int, int]:
        return {r: h for op, r, h in self.ops
                if op in ("match", "sub") and r is not None and h is not None}

    def span_to_hyp(self, start: int, end: int) -> list[int]:
        """Hypothesis token indices covering reference tokens [start, end).

        Insertions inside the span count. One reference token "4321" is often
        two hypothesis tokens, because ASR writes "4,321" and the normaliser
        splits on the comma. Taking only the aligned pairs would read that as
        "4" and score the entity wrong when the system in fact heard it right,
        so the metric would be measuring punctuation.
        """
        positions = [k for k, (op, r, h) in enumerate(self.ops)
                     if r is not None and start <= r < end]
        if not positions:
            return []
        lo, hi = min(positions), max(positions)
        # Absorb insertions touching either end of the span. A split token can
        # align either half, so "4321" against "4 321" puts the other half on
        # whichever side the equal-cost backtrace happened to choose.
        while hi + 1 < len(self.ops) and self.ops[hi + 1][0] == "ins":
            hi += 1
        while lo - 1 >= 0 and self.ops[lo - 1][0] == "ins":
            lo -= 1
        return [h for op, r, h in self.ops[lo:hi + 1] if h is not None]


def align(ref: list[str], hyp: list[str]) -> Alignment:
    """Levenshtein alignment with backpointers. O(|ref| * |hyp|)."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    bp = np.zeros((n + 1, m + 1), dtype=np.int8)     # 0 diag, 1 up (del), 2 left (ins)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    bp[1:, 0] = 1
    bp[0, 1:] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            choices = (d[i - 1, j - 1] + cost, d[i - 1, j] + 1, d[i, j - 1] + 1)
            k = int(np.argmin(choices))
            d[i, j] = choices[k]
            bp[i, j] = k
    ops: list[tuple[Op, int | None, int | None]] = []
    i, j = n, m
    sub = dele = ins = match = 0
    while i > 0 or j > 0:
        k = bp[i, j]
        if i > 0 and j > 0 and k == 0:
            if ref[i - 1] == hyp[j - 1]:
                ops.append(("match", i - 1, j - 1)); match += 1
            else:
                ops.append(("sub", i - 1, j - 1)); sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and (k == 1 or j == 0):
            ops.append(("del", i - 1, None)); dele += 1
            i -= 1
        else:
            ops.append(("ins", None, j - 1)); ins += 1
            j -= 1
    ops.reverse()
    return Alignment(ops, sub, dele, ins, match)


def wer(reference: str, hypothesis: str) -> dict:
    """WER = (S + D + I) / N."""
    ref, hyp = normalize_tokens(reference), normalize_tokens(hypothesis)
    a = align(ref, hyp)
    n = len(ref)
    return {"wer": (a.errors / n) if n else (0.0 if not hyp else 1.0),
            "substitutions": a.substitutions, "deletions": a.deletions,
            "insertions": a.insertions, "ref_words": n, "hyp_words": len(hyp),
            "alignment": a}


def corpus_wer(pairs: list[tuple[str, str]]) -> dict:
    """Pooled WER over a corpus, which is the correct aggregate. Averaging
    per-utterance WER over-weights short utterances."""
    S = D = I = N = 0
    for ref, hyp in pairs:
        r = wer(ref, hyp)
        S += r["substitutions"]; D += r["deletions"]; I += r["insertions"]
        N += r["ref_words"]
    return {"wer": (S + D + I) / N if N else 0.0, "substitutions": S,
            "deletions": D, "insertions": I, "ref_words": N, "utterances": len(pairs)}


# ---------------------------------------------------------------- entity level

def _canonical(entity_type: str, text: str) -> str:
    """Normalise a surface form so that the spellings of one value agree.

    "fifty thousand", "50,000" and the tokenised "50 000" that comes out of the
    aligner all have to reduce to 50000, or the metric measures transcription
    formatting rather than whether the system heard the right amount.
    """
    from ..pipeline.slots import parse_amount
    t = (text or "").strip().lower()
    if entity_type == "amount":
        v = parse_amount(t)
        if v is not None:
            return f"{v:.0f}"
        # ASR writes amounts as digits with separators, which the word parser
        # deliberately refuses to read as money. Fall back to the digits.
        digits = re.sub(r"\D", "", t)
        return digits.lstrip("0") or digits if digits else t
    if entity_type in ("card_last4", "account_number", "cheque_number"):
        digits = re.sub(r"\D", "", t)
        return digits[-4:] if entity_type == "card_last4" else digits
    return re.sub(r"\s+", " ", t)


def locate_entity(ref_tokens: list[str], entity: dict, max_span: int = 4) -> tuple[int, int] | None:
    """Find the token span in the reference that realises this entity.

    Tried as n-grams rather than by string search, because an amount is written
    "50000" in the label and spoken as "fifty thousand" in the transcript.
    """
    target = _canonical(entity["type"], entity["value"])
    for span in range(1, max_span + 1):
        for start in range(0, len(ref_tokens) - span + 1):
            candidate = " ".join(ref_tokens[start:start + span])
            if _canonical(entity["type"], candidate) == target:
                return start, start + span
    return None


def entity_error_rate(items: list[dict]) -> dict:
    """EER_s = (1/|E|) * sum 1[e_hat != e], per entity type and overall.

    Each reference entity span is mapped onto hypothesis tokens through the WER
    alignment, and the mapped text is compared with the labelled value. An
    entity whose reference span cannot be located is counted as an error, not
    skipped, because silently dropping hard cases would flatter the number.
    """
    per_type: dict[str, dict] = {}
    total = errors = 0
    details = []
    per_language: dict[str, dict] = {}
    for item in items:
        ref_tokens = normalize_tokens(item["reference"])
        hyp_tokens = normalize_tokens(item["hypothesis"])
        alignment = align(ref_tokens, hyp_tokens)
        lang = item.get("language", "unknown")
        for ent in item.get("entities", []):
            etype = ent["type"]
            bucket = per_type.setdefault(etype, {"n": 0, "errors": 0})
            lbucket = per_language.setdefault(lang, {"n": 0, "errors": 0})
            bucket["n"] += 1
            lbucket["n"] += 1
            total += 1
            span = locate_entity(ref_tokens, ent)
            if span is None:
                bucket["errors"] += 1
                lbucket["errors"] += 1
                errors += 1
                details.append({"id": item.get("id"), "type": etype, "language": lang,
                                "expected": ent["value"], "got": None, "correct": False,
                                "reason": "entity not locatable in the reference"})
                continue
            hyp_idx = alignment.span_to_hyp(*span)
            got = " ".join(hyp_tokens[i] for i in sorted(set(hyp_idx))) if hyp_idx else ""
            ok = _canonical(etype, got) == _canonical(etype, ent["value"])
            if not ok:
                bucket["errors"] += 1
                lbucket["errors"] += 1
                errors += 1
            details.append({"id": item.get("id"), "type": etype, "language": lang,
                            "expected": ent["value"], "got": got, "correct": ok})
    for bucket in list(per_type.values()) + list(per_language.values()):
        bucket["error_rate"] = bucket["errors"] / bucket["n"] if bucket["n"] else 0.0
    return {"entity_error_rate": errors / total if total else 0.0,
            "n_entities": total, "errors": errors, "per_type": per_type,
            "per_language": per_language, "details": details}


# ---------------------------------------------------------------- retrieval

def recall_at_k(results: list[tuple[list[str], str]]) -> float:
    """results: (retrieved doc_ids, expected doc_id)."""
    if not results:
        return 0.0
    return sum(1 for got, want in results if want in got) / len(results)


MIN_PRECISION = 0.90


def _scores_at(a: np.ndarray, u: np.ndarray, d: float) -> dict:
    tp = float(np.sum(a >= d)); fn = float(np.sum(a < d)); fp = float(np.sum(u >= d))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"delta": round(float(d), 4), "f1": round(f1, 4),
            "precision": round(precision, 4), "recall": round(recall, 4)}


def calibrate_delta(scores_answerable: list[float], scores_unanswerable: list[float],
                    grid: np.ndarray | None = None,
                    min_precision: float = MIN_PRECISION) -> dict:
    """Pick the similarity floor, and report what the choice costs.

    Two candidates, because they disagree and the disagreement matters.

    **F1-optimal** maximises F1 over the evaluation set. It is what the brief
    asks for, and on a 54-item set it over-fits: the tuned value landed on
    0.59, and a real spoken question about home loan rates then scored 0.58
    and was refused. Losing an answer by one hundredth is a coincidence, not a
    threshold.

    **Precision-constrained** is the one the system uses: the LOWEST floor
    whose precision still clears `min_precision`. Same guarantee against
    grounding on an irrelevant passage, but it stops paying for precision the
    refusal path does not need. The asymmetry is deliberate. A weak passage is
    still cited, still version-stamped, and still gated by the confidence and
    tier machinery downstream; a wrong refusal just sends the customer away
    with nothing.

    Both are reported, with the precision and recall each one gives.
    """
    grid = np.arange(0.05, 0.95, 0.005) if grid is None else grid
    a = np.asarray(scores_answerable, dtype=float)
    u = np.asarray(scores_unanswerable, dtype=float)
    if not len(a):
        return {"delta": 0.42, "f1": 0.0, "precision": 0.0, "recall": 0.0,
                "n_answerable": 0, "n_unanswerable": int(len(u)),
                "method": "default, no answerable queries to calibrate on"}

    rows = [_scores_at(a, u, d) for d in grid]
    f1_best = max(rows, key=lambda r: r["f1"])
    ok = [r for r in rows if r["precision"] >= min_precision and r["recall"] > 0]
    chosen = min(ok, key=lambda r: r["delta"]) if ok else f1_best

    out = dict(chosen)
    out.update({
        "method": (f"lowest floor whose precision still clears {min_precision:.0%}"
                   if ok else
                   f"fell back to F1-optimal: no floor reaches {min_precision:.0%} precision"),
        "min_precision": min_precision,
        "f1_optimal": f1_best,
        "n_answerable": int(len(a)),
        "n_unanswerable": int(len(u)),
        "min_answerable_score": round(float(np.min(a)), 4),
        "max_unanswerable_score": round(float(np.max(u)), 4) if len(u) else None,
    })
    return out


# ---------------------------------------------------------------- biometrics

def eer(target: np.ndarray, nontarget: np.ndarray) -> dict:
    from ..security.speaker import eer as _eer
    value, threshold = _eer(np.asarray(target), np.asarray(nontarget))
    return {"eer": round(float(value), 4), "threshold": round(float(threshold), 4),
            "n_target": int(len(target)), "n_nontarget": int(len(nontarget))}


def min_tdcf(cm_bona: np.ndarray, cm_spoof: np.ndarray,
             asv_p_miss: float, asv_p_fa: float, asv_p_fa_spoof: float) -> dict:
    """Normalised minimum tandem detection cost function.

    Follows the ASVspoof 2019 formulation with the ASV system fixed at its own
    operating point:

        C1 = pi_tar * (C_miss - C_miss * P_miss_asv) - pi_non * C_fa * P_fa_asv
        C2 = C_fa * pi_spoof * P_fa_spoof_asv
        t-DCF_norm(s) = (C1 * P_miss_cm(s) + C2 * P_fa_cm(s)) / min(C1, C2)

    The cost constants and priors are in config.py, and RESULTS.md prints them
    beside the number so the value can be reproduced.
    """
    from ..config import TDCF_C_FA, TDCF_C_MISS, TDCF_P_SPOOF, TDCF_P_TARGET
    pi_tar, pi_spoof = TDCF_P_TARGET, TDCF_P_SPOOF
    pi_non = max(0.0, 1.0 - pi_tar - pi_spoof)
    C1 = pi_tar * (TDCF_C_MISS - TDCF_C_MISS * asv_p_miss) - pi_non * TDCF_C_FA * asv_p_fa
    C2 = TDCF_C_FA * pi_spoof * asv_p_fa_spoof
    priors = {"pi_target": pi_tar, "pi_nontarget": pi_non, "pi_spoof": pi_spoof}
    costs = {"C_miss": TDCF_C_MISS, "C_fa": TDCF_C_FA}
    if min(C1, C2) <= 0:
        # Not a failure, a degenerate operating point, and worth saying so in
        # words. C2 goes to zero when the verification system rejects every
        # spoof on its own at its chosen threshold, which leaves the
        # countermeasure carrying no cost and the normalised t-DCF undefined.
        reason = ("the speaker verification system already rejects every spoof at its "
                  "own threshold, so the countermeasure carries no tandem cost"
                  if C2 <= 0 else
                  "the cost of a miss is outweighed by the verification system's own "
                  "error rates at this operating point")
        return {"min_tdcf": None, "defined": False, "reason": reason,
                "C1": round(float(C1), 6), "C2": round(float(C2), 6),
                "priors": priors, "costs": costs,
                "n_bona": int(len(cm_bona)), "n_spoof": int(len(cm_spoof))}
    thresholds = np.unique(np.concatenate([cm_bona, cm_spoof]))
    best, best_t = np.inf, None
    for t in thresholds:
        p_miss_cm = float(np.mean(cm_bona < t))
        p_fa_cm = float(np.mean(cm_spoof >= t))
        value = (C1 * p_miss_cm + C2 * p_fa_cm) / min(C1, C2)
        if value < best:
            best, best_t = value, float(t)
    return {"min_tdcf": round(float(best), 4), "defined": True,
            "threshold": round(best_t, 4),
            "C1": round(float(C1), 6), "C2": round(float(C2), 6),
            "priors": priors, "costs": costs,
            "n_bona": int(len(cm_bona)), "n_spoof": int(len(cm_spoof))}


# ---------------------------------------------------------------- latency

def latency_from_traces(traces: list[dict]) -> dict:
    """p50 and p95 per stage, straight off the trace timings."""
    buckets: dict[str, list[float]] = {}
    totals: list[float] = []
    for t in traces:
        total = 0.0
        for stage in t.get("stages", []):
            buckets.setdefault(stage["stage"], []).append(stage["duration_ms"])
            total += stage["duration_ms"]
        totals.append(total)
    def pct(values: list[float], q: float) -> float:
        ordered = sorted(values)
        return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2)
    out = {name: {"n": len(v), "p50_ms": pct(v, 0.5), "p95_ms": pct(v, 0.95)}
           for name, v in buckets.items()}
    if totals:
        out["_turn_total"] = {"n": len(totals), "p50_ms": pct(totals, 0.5),
                              "p95_ms": pct(totals, 0.95)}
    return out


def demo() -> None:
    r = wer("block my card ending four three two one",
            "block my card ending four three two one")
    assert r["wer"] == 0.0
    r = wer("transfer fifty thousand rupees to rohan",
            "transfer fifteen thousand rupees to rohan")
    assert r["substitutions"] == 1 and abs(r["wer"] - 1 / 6) < 1e-9, r

    out = entity_error_rate([
        {"id": "a", "reference": "transfer fifty thousand rupees to Rohan",
         "hypothesis": "transfer fifty thousand rupees to Rohan",
         "entities": [{"type": "amount", "value": "50000"},
                      {"type": "payee", "value": "Rohan"}]},
        {"id": "b", "reference": "transfer fifty thousand rupees to Rohan",
         "hypothesis": "transfer fifteen thousand rupees to Rohan",
         "entities": [{"type": "amount", "value": "50000"}]},
    ])
    assert out["n_entities"] == 3 and out["errors"] == 1, out
    assert abs(out["per_type"]["amount"]["error_rate"] - 0.5) < 1e-9, out
    print("metrics ok", round(out["entity_error_rate"], 3))
