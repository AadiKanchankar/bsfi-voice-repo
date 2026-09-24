"""Baseline against baseline-plus-CLU, on the cases the baseline is expected
to struggle with.

The point of the experiment is to find out whether the language layer earns
its place, so the baseline is never removed and both are measured on exactly
the same inputs in the same run. If the CLU does not win here, the honest
outcome is to leave BFSI_CLU_PROVIDER=null and say so in the paper.

`make clu-eval` writes docs/CLU_RESULTS.md. Nothing in that file is typed by
hand, and a run against the mock provider refuses to produce numbers at all,
because keyword rules are not a language model and reporting them as one
would be the exact dishonesty the capability registry exists to prevent.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..config import CLU_MODEL, CLU_PROVIDER, EVAL_DIR, RUNTIME_DIR
from ..trace import utcnow

CASES = EVAL_DIR / "clu_cases.json"
RESULTS_MD = Path(__file__).resolve().parents[3] / "docs" / "CLU_RESULTS.md"


def load_cases() -> dict:
    return json.loads(CASES.read_text(encoding="utf-8"))


def _entities_match(expected: dict, got: dict) -> bool:
    """Every expected entity present and equal. Extra entities are allowed:
    over-extraction is a different failure and is counted separately."""
    for key, want in (expected or {}).items():
        if key not in got:
            return False
        have = got[key]
        if isinstance(want, (int, float)):
            try:
                if abs(float(have) - float(want)) > 0.01:
                    return False
            except (TypeError, ValueError):
                return False
        elif str(have).strip().lower() != str(want).strip().lower():
            return False
    return True


def run_baseline(cases: list[dict]) -> list[dict]:
    """The deterministic classifier alone, exactly as the frozen snapshot."""
    from ..pipeline import langid, nlu, slots
    rows = []
    for case in cases:
        t0 = time.perf_counter()
        out = nlu.classify(case["text"])
        extracted = slots.extract(case["text"], out["intent"])
        lid = langid.identify(case["text"])
        rows.append({
            "id": case["id"], "group": case["group"],
            "intent": out["intent"], "confidence": round(out["confidence"], 4),
            "sub_intents": [],            # the baseline has no concept of these
            "entities": extracted,
            "code_mixed": (lid["code_mix_index"] or 0) > 0,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "called_model": False,
        })
    return rows


def run_with_clu(cases: list[dict], pace_s: float = 0.0) -> list[dict]:
    """Deterministic classifier, then the CLU on the turns the router picks.

    `pace_s` spaces the calls out. Free tiers cap input tokens per minute, and
    firing forty cases at once burns the budget in seconds and then measures
    the fallback path instead of the model, which is what the first run of
    this harness actually did.
    """
    from .. import clu
    from ..pipeline import langid, nlu, slots
    rows = []
    for case in cases:
        t0 = time.perf_counter()
        base = nlu.classify(case["text"])
        extracted = slots.extract(case["text"], base["intent"])
        lid = langid.identify(case["text"])
        outcome = clu.understand_turn(
            case["text"], context=case.get("context"),
            baseline_confidence=base["confidence"], baseline_margin=base["margin"],
            code_mix_index=lid["code_mix_index"] or 0.0)
        merged = clu.merge_with_baseline(base["intent"], base["confidence"],
                                         extracted, outcome)
        r = outcome.result
        rows.append({
            "id": case["id"], "group": case["group"],
            "intent": merged["intent"], "confidence": round(merged["confidence"], 4),
            "sub_intents": merged["sub_intents"], "entities": merged["slots"],
            "code_mixed": bool(r.code_mixed) if r else (lid["code_mix_index"] or 0) > 0,
            "languages": list(r.languages) if r else [],
            "references": merged["references"],
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "called_model": outcome.called,
            "source": merged["source"],
            "override_blocked": merged["override_blocked"],
            "error": outcome.error,
            "prompt_tokens": outcome.prompt_tokens,
            "completion_tokens": outcome.completion_tokens,
            "retries": (outcome.meta or {}).get("retries", 0),
        })
        if pace_s and outcome.called:
            time.sleep(pace_s)
    return rows


def score(cases: list[dict], rows: list[dict]) -> dict:
    by_id = {r["id"]: r for r in rows}
    per_group: dict[str, dict] = {}
    intent_ok = ent_total = ent_ok = 0
    compound_total = compound_ok = 0
    context_total = context_ok = 0
    refuse_total = refuse_ok = 0
    escalate_total = escalate_ok = 0
    cm_total = cm_ok = 0
    failures = []

    for case in cases:
        r = by_id[case["id"]]
        g = per_group.setdefault(case["group"], {"n": 0, "intent_ok": 0})
        g["n"] += 1
        ok = r["intent"] == case["expected_intent"]
        intent_ok += ok
        g["intent_ok"] += ok
        if not ok:
            failures.append({"id": case["id"], "group": case["group"],
                             "text": case["text"][:60],
                             "expected": case["expected_intent"], "got": r["intent"]})

        if case.get("expected_sub_intents") is not None:
            compound_total += 1
            compound_ok += set(case["expected_sub_intents"]).issubset(set(r["sub_intents"]))
        if case.get("needs_context"):
            context_total += 1
            context_ok += ok
        if case.get("must_refuse"):
            refuse_total += 1
            refuse_ok += r["intent"] == "out_of_scope"
        if case.get("must_escalate"):
            escalate_total += 1
            from ..config import HARD_TIER3_INTENTS
            escalate_ok += r["intent"] in HARD_TIER3_INTENTS
        if case.get("expected_entities"):
            ent_total += 1
            ent_ok += _entities_match(case["expected_entities"], r["entities"])
        if case["group"] in ("hinglish", "maringlish"):
            cm_total += 1
            cm_ok += bool(r.get("code_mixed"))

    for g in per_group.values():
        g["accuracy"] = round(g["intent_ok"] / g["n"], 4) if g["n"] else 0.0

    lat = sorted(r["latency_ms"] for r in rows)
    called = [r for r in rows if r.get("called_model")]
    return {
        "n": len(cases),
        "intent_accuracy": round(intent_ok / len(cases), 4) if cases else 0.0,
        "per_group": dict(sorted(per_group.items())),
        "compound": {"n": compound_total,
                     "accuracy": round(compound_ok / compound_total, 4) if compound_total else None},
        "context": {"n": context_total,
                    "accuracy": round(context_ok / context_total, 4) if context_total else None},
        "must_refuse": {"n": refuse_total,
                        "accuracy": round(refuse_ok / refuse_total, 4) if refuse_total else None},
        "must_escalate": {"n": escalate_total,
                          "accuracy": round(escalate_ok / escalate_total, 4) if escalate_total else None},
        "entities": {"n": ent_total,
                     "accuracy": round(ent_ok / ent_total, 4) if ent_total else None},
        "code_mix_detection": {"n": cm_total,
                               "accuracy": round(cm_ok / cm_total, 4) if cm_total else None},
        "latency_ms": {"p50": lat[len(lat) // 2] if lat else 0,
                       "p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else 0},
        "model_calls": len(called),
        "call_rate": round(len(called) / len(rows), 4) if rows else 0.0,
        "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in called) or None,
        "completion_tokens": sum(r.get("completion_tokens") or 0 for r in called) or None,
        "errors": [r for r in rows if r.get("error")],
        "overrides_blocked": sum(1 for r in rows if r.get("override_blocked")),
        "failures": failures,
    }


def run_all(write: bool = True, pace_s: float | None = None) -> dict:
    data = load_cases()
    cases = data["cases"]
    base_rows = run_baseline(cases)
    # Default pacing keeps a free tier inside its tokens-per-minute budget.
    if pace_s is None:
        pace_s = float(os.environ.get("BFSI_CLU_EVAL_PACE", "4.5"))
    # A live turn gives the CLU three seconds and then goes on without it,
    # because a caller is waiting. Here nobody is waiting, and cutting a
    # rate-limited call short would measure the free tier rather than the
    # model, which is exactly the mistake that made the first CLU evaluation
    # meaningless. So the deadline is lifted for the duration of the run.
    os.environ.setdefault("BFSI_CLU_DEADLINE", "120")
    import importlib
    from .. import config as cfg
    cfg.CLU_DEADLINE_S = float(os.environ["BFSI_CLU_DEADLINE"])
    from ..clu import providers as _providers
    importlib.reload(_providers)
    clu_rows = run_with_clu(cases, pace_s=pace_s)
    out = {
        "generated_at": utcnow().isoformat(),
        "provider": CLU_PROVIDER, "model": CLU_MODEL,
        "n_cases": len(cases), "pace_s": pace_s,
        "baseline": score(cases, base_rows),
        "with_clu": score(cases, clu_rows),
        "rows": {"baseline": base_rows, "with_clu": clu_rows},
    }
    if write:
        RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_MD.write_text(render(out))
        (RUNTIME_DIR / "clu_results.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "n/a"
    d = b - a
    return f"{d:+.4f}" if abs(d) > 1e-9 else "no change"


def render(r: dict) -> str:
    b, c = r["baseline"], r["with_clu"]
    provider = r["provider"]
    out = ["# CLU experiment results\n\n"]

    if provider in ("null", "mock"):
        out.append(
            f"> **No numbers in this run.** The provider was `{provider}`, which is "
            f"{'disabled' if provider == 'null' else 'a keyword-rule stand-in, not a language model'}. "
            f"Reporting it as a language-model result would be exactly the kind of "
            f"overclaim the capability registry exists to prevent. Set "
            f"`BFSI_CLU_PROVIDER` to a real provider and run `make clu-eval` again.\n\n")
        out.append(f"Baseline intent accuracy on the {r['n_cases']} case set: "
                   f"**{b['intent_accuracy']}**. That is the number to beat.\n\n")
        out.append("## Baseline, by group\n\n| Group | n | Accuracy |\n|---|---|---|\n")
        for g, v in b["per_group"].items():
            out.append(f"| {g} | {v['n']} | {v['accuracy']} |\n")
        return "".join(out)

    out.append(
        f"Generated by `make clu-eval`, which runs both systems over the same "
        f"{r['n_cases']} cases in one pass. Provider `{provider}`, model "
        f"`{r['model']}`. Generated {r['generated_at']}.\n\n")
    out.append(
        "The cases in `data/eval/clu_cases.json` are deliberately the ones the "
        "deterministic classifier is expected to struggle with: code-mixing, "
        "romanised Hindi and Marathi, compound requests, follow-ups that only mean "
        "something in context, and probes that must still be refused. A baseline "
        "score here is not comparable with the accuracy in RESULTS.md, which is "
        "measured on an easier set.\n\n")

    out.append("## Headline\n\n| Metric | Baseline | With CLU | Change |\n|---|---|---|---|\n")
    rows = [
        ("Intent accuracy", b["intent_accuracy"], c["intent_accuracy"]),
        ("Compound requests", b["compound"]["accuracy"], c["compound"]["accuracy"]),
        ("Context resolution", b["context"]["accuracy"], c["context"]["accuracy"]),
        ("Entity extraction", b["entities"]["accuracy"], c["entities"]["accuracy"]),
        ("Code-mix detection", b["code_mix_detection"]["accuracy"], c["code_mix_detection"]["accuracy"]),
        ("Must-refuse held", b["must_refuse"]["accuracy"], c["must_refuse"]["accuracy"]),
        ("Must-escalate held", b["must_escalate"]["accuracy"], c["must_escalate"]["accuracy"]),
    ]
    for label, bv, cv in rows:
        out.append(f"| {label} | {bv} | {cv} | {_delta(bv, cv)} |\n")

    out.append("\n## By language and case type\n\n"
               "| Group | n | Baseline | With CLU | Change |\n|---|---|---|---|---|\n")
    for g in sorted(set(b["per_group"]) | set(c["per_group"])):
        bg = b["per_group"].get(g, {})
        cg = c["per_group"].get(g, {})
        out.append(f"| {g} | {bg.get('n', cg.get('n'))} | {bg.get('accuracy')} | "
                   f"{cg.get('accuracy')} | {_delta(bg.get('accuracy'), cg.get('accuracy'))} |\n")

    out.append("\n## Cost and latency\n\n| Metric | Baseline | With CLU |\n|---|---|---|\n")
    out.append(f"| p50 latency | {b['latency_ms']['p50']} ms | {c['latency_ms']['p50']} ms |\n")
    out.append(f"| p95 latency | {b['latency_ms']['p95']} ms | {c['latency_ms']['p95']} ms |\n")
    out.append(f"| Turns reaching the model | 0 | {c['model_calls']} of {r['n_cases']} "
               f"({c['call_rate']:.0%}) |\n")
    if c.get("prompt_tokens"):
        out.append(f"| Tokens in / out | n/a | {c['prompt_tokens']} / "
                   f"{c['completion_tokens']} |\n")
    out.append("\nThe router only calls the model when the deterministic head is unsure, "
               "the utterance is code-mixed, or it looks like a follow-up. The call rate "
               "above is on a set chosen to be hard; on ordinary traffic it is lower.\n")

    out.append("\n## Safety\n\n")
    out.append(f"- Downgrades refused by the safety floor: **{c['overrides_blocked']}**. "
               f"The language layer may raise the assessed risk of a turn and never "
               f"lower it below a confident deterministic reading.\n")
    out.append(f"- Must-refuse cases still refused: **{c['must_refuse']['accuracy']}** "
               f"over {c['must_refuse']['n']} cases, including a prompt-injection probe.\n")
    out.append(f"- Must-escalate cases still escalated: **{c['must_escalate']['accuracy']}** "
               f"over {c['must_escalate']['n']} cases.\n")
    if c["errors"]:
        out.append(f"- Provider errors during the run: {len(c['errors'])}. Each one fell "
                   f"back to the deterministic reading, which is the designed behaviour.\n")

    for label, s in (("Baseline", b), ("With CLU", c)):
        if s["failures"]:
            out.append(f"\n## {label} failures ({len(s['failures'])})\n\n"
                       "| id | group | said | expected | got |\n|---|---|---|---|---|\n")
            for f in s["failures"]:
                out.append(f"| {f['id']} | {f['group']} | {f['text']} | "
                           f"{f['expected']} | {f['got']} |\n")

    out.append("\n## Reproducing\n\n```\nBFSI_CLU_PROVIDER=openai make clu-eval\n```\n")
    return "".join(out)
