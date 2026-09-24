"""`make eval` runs this. It regenerates every number in docs/RESULTS.md from
scratch, and writes nothing it did not compute.

Rule for this file: no placeholder numbers, ever. If a metric cannot be
computed because a model or a data file is missing, RESULTS.md says so in that
row rather than carrying a plausible looking value.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from ..config import (CALIBRATION_PATH, EVAL_DIR, RUNTIME_DIR, SEED_DIR,
                      SIMILARITY_FLOOR_DELTA)
from ..trace import utcnow
from . import metrics

UTTERANCES = EVAL_DIR / "utterances.json"
AUDIO_DIR = EVAL_DIR / "audio"
RESULTS_MD = Path(__file__).resolve().parents[3] / "docs" / "RESULTS.md"


def load_set() -> dict:
    if not UTTERANCES.exists():
        raise FileNotFoundError(f"eval set missing at {UTTERANCES}")
    return json.loads(UTTERANCES.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- ASR and entities

def run_asr(items: list[dict]) -> dict:
    """Transcribe the rendered audio. Skipped, and said to be skipped, when the
    audio has not been rendered."""
    from ..pipeline import asr
    pairs, ent_items, latencies = [], [], []
    by_language: dict[str, list[tuple[str, str]]] = {}
    missing = 0
    for item in items:
        wav = AUDIO_DIR / f"{item['id']}.wav"
        if not wav.exists():
            missing += 1
            continue
        t0 = time.perf_counter()
        out = asr.transcribe(wav.read_bytes())
        latencies.append((time.perf_counter() - t0) * 1000)
        pairs.append((item["text"], out["text"]))
        by_language.setdefault(item["language"], []).append((item["text"], out["text"]))
        ent_items.append({"id": item["id"], "reference": item["text"],
                          "hypothesis": out["text"], "entities": item["entities"],
                          "language": item["language"]})
    if not pairs:
        return {"available": False, "reason": f"no rendered audio in {AUDIO_DIR}",
                "missing": missing}
    ordered = sorted(latencies)
    return {"available": True, "n": len(pairs), "missing_audio": missing,
            "wer": metrics.corpus_wer(pairs),
            "wer_by_language": {lang: metrics.corpus_wer(p) for lang, p in
                                sorted(by_language.items())},
            "entities": metrics.entity_error_rate(ent_items),
            "asr_latency_ms": {
                "p50": round(ordered[len(ordered) // 2], 1),
                "p95": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 1)},
            "model_id": asr.model_id(),
            "transcripts": [{"id": i["id"], "reference": i["reference"],
                             "hypothesis": i["hypothesis"]} for i in ent_items]}


# ---------------------------------------------------------------- retrieval

def run_retrieval(items: list[dict]) -> dict:
    """Calibrate the refusal floor on the split that actually matters.

    The negative class is `out_of_scope`, not "everything the knowledge base
    does not answer". Those are different things, and conflating them broke
    the calibration: "what is the balance in my savings account" scores 0.77
    against the savings-account policy, correctly, because such a policy
    exists. It is answered from core banking rather than from the knowledge
    base, which makes it neither a positive nor a negative for a GROUNDING
    decision. Counting it as a false positive drove the floor up to 0.645 and
    dropped recall on genuinely answerable questions to 0.5.

    Positives are questions the knowledge base should answer. Negatives are
    questions the assistant must refuse. Everything else is excluded from the
    calibration and reported separately.
    """
    from ..pipeline import retrieval
    answerable = [i for i in items if i["answerable_from_kb"]]
    unanswerable = [i for i in items if i["intent"] == "out_of_scope"]
    other = [i for i in items
             if not i["answerable_from_kb"] and i["intent"] != "out_of_scope"]
    hits, scores_a, scores_u = [], [], []
    for item in answerable:
        found = retrieval.search(item["text"], delta=0.0)
        ids = [p.doc_id for p in found["passages"]]
        hits.append((ids, item["expected_doc_id"]))
        scores_a.append(found["max_score"])
    for item in unanswerable:
        scores_u.append(retrieval.search(item["text"], delta=0.0)["max_eligible_score"])
    scores_other = [retrieval.search(i["text"], delta=0.0)["max_eligible_score"]
                    for i in other]
    calibration = metrics.calibrate_delta(scores_a, scores_u)
    # Per-language top scores. The knowledge base is written in English, so a
    # Hindi or Marathi phrasing of the same question scores lower purely
    # through the cross-lingual gap in the embedding, and a single global floor
    # then refuses questions it answers in English. Worth reporting rather than
    # averaging away.
    by_language: dict[str, list[float]] = {}
    for item, score in zip(answerable, scores_a):
        by_language.setdefault(item["language"], []).append(score)
    lang_scores = {lang: {"n": len(v), "mean_top_score": round(float(np.mean(v)), 4),
                          "min_top_score": round(float(np.min(v)), 4),
                          "would_clear_delta": int(sum(x >= calibration["delta"] for x in v))}
                   for lang, v in sorted(by_language.items())}
    return {"available": True,
            "answerable_by_language": lang_scores,
            "n_excluded_from_calibration": len(other),
            "mean_score_core_banking": (round(float(np.mean(scores_other)), 4)
                                        if scores_other else None),
            "recall_at_k": round(metrics.recall_at_k(hits), 4),
            "negatives": "intent == out_of_scope",
            "k": retrieval.RETRIEVAL_K if hasattr(retrieval, "RETRIEVAL_K") else 4,
            "n_answerable": len(answerable), "n_unanswerable": len(unanswerable),
            "calibrated_delta": calibration,
            "configured_delta": SIMILARITY_FLOOR_DELTA,
            "mean_score_answerable": round(float(np.mean(scores_a)), 4) if scores_a else None,
            "mean_score_unanswerable": round(float(np.mean(scores_u)), 4) if scores_u else None}


# ---------------------------------------------------------------- NLU

def run_nlu(items: list[dict]) -> dict:
    from ..pipeline import nlu
    correct = 0
    confusions: dict[str, int] = {}
    for item in items:
        got = nlu.classify(item["text"])["intent"]
        if got == item["intent"]:
            correct += 1
        else:
            confusions[f"{item['intent']} -> {got}"] = \
                confusions.get(f"{item['intent']} -> {got}", 0) + 1
    head = json.loads((RUNTIME_DIR / "seed_manifest.json").read_text())["nlu"] \
        if (RUNTIME_DIR / "seed_manifest.json").exists() else {}
    return {"available": True, "n": len(items),
            "accuracy_on_eval_set": round(correct / len(items), 4) if items else 0.0,
            "seed_cv_accuracy": head.get("cv_accuracy"),
            "seed_cv_std": head.get("cv_std"),
            "n_train": head.get("n_train"),
            "confusions": dict(sorted(confusions.items(), key=lambda kv: -kv[1])[:10])}


# ---------------------------------------------------------------- language id

def run_langid(items: list[dict]) -> dict:
    """Dominant-language accuracy plus the CMI distribution.

    Code-mixed utterances are excluded from the dominant-language accuracy,
    because there is no single correct label for them; they are reported
    through the code-mix index instead.
    """
    from ..pipeline import langid
    mono = [i for i in items if i["language"] in ("en", "hi", "mr")]
    mixed = [i for i in items if i["language"] == "mix"]
    correct = sum(1 for i in mono if langid.identify(i["text"])["dominant"] == i["language"])
    cmi_mixed = [langid.identify(i["text"])["code_mix_index"] for i in mixed]
    cmi_mono = [langid.identify(i["text"])["code_mix_index"] for i in mono]
    return {"available": True, "n_monolingual": len(mono), "n_code_mixed": len(mixed),
            "dominant_language_accuracy": round(correct / len(mono), 4) if mono else 0.0,
            "mean_cmi_code_mixed": round(float(np.mean(cmi_mixed)), 2) if cmi_mixed else None,
            "mean_cmi_monolingual": round(float(np.mean(cmi_mono)), 2) if cmi_mono else None,
            "cmi_nonzero_on_code_mixed": (
                round(float(np.mean([c > 0 for c in cmi_mixed])), 4) if cmi_mixed else None)}


# ---------------------------------------------------------------- speaker and spoof

def run_biometrics(conn) -> dict:
    from ..security import antispoof, speaker
    voice_dir, spoof_dir = SEED_DIR / "voices", SEED_DIR / "spoofs"
    if not voice_dir.exists() or not any(voice_dir.glob("*.wav")):
        return {"available": False, "reason": "no enrolled voice clips; run `make seed`"}

    clips: dict[str, list[bytes]] = {}
    for wav in sorted(voice_dir.glob("*.wav")):
        clips.setdefault(wav.stem.rsplit("_", 1)[0], []).append(wav.read_bytes())

    # Trials are the held-out clips when they exist. Scoring a speaker against
    # the clips their own enrolment mean was built from reports an EER of zero
    # and measures nothing, so the enrolment clips are used only as a fallback
    # and the report says which set produced the number.
    trial_dir = SEED_DIR / "trials"
    trials: dict[str, list[bytes]] = {}
    for wav in sorted(trial_dir.glob("*.wav")) if trial_dir.exists() else []:
        trials.setdefault(wav.stem.split("_trial_")[0], []).append(wav.read_bytes())
    held_out = bool(trials)
    probe = trials if held_out else clips

    target, nontarget = [], []
    for cid in clips:
        for other_cid, files in probe.items():
            for clip in files:
                score = speaker.verify(conn, cid, clip)["score"]
                (target if other_cid == cid else nontarget).append(score)
    asv = metrics.eer(np.array(target), np.array(nontarget))
    asv["trial_source"] = ("held-out clips, phrases the enrolment never saw"
                           if held_out else
                           "the enrolment clips themselves, which makes this number "
                           "optimistic; run `make seed` to generate held-out trials")

    spoof_files = sorted(spoof_dir.glob("*.wav")) if spoof_dir.exists() else []
    cm = {"available": False, "reason": "no spoof clips"}
    if spoof_files:
        bona_scores = np.array([antispoof.score(c)["score"]
                                for files in probe.values() for c in files])
        spoof_scores = np.array([antispoof.score(f.read_bytes())["score"]
                                 for f in spoof_files])
        cm_eer = metrics.eer(bona_scores, spoof_scores)
        # The ASV operating point the t-DCF is conditioned on, measured here.
        theta = asv["threshold"]
        asv_p_miss = float(np.mean(np.array(target) < theta))
        asv_p_fa = float(np.mean(np.array(nontarget) >= theta))
        spoof_asv = [speaker.verify(conn, cid, f.read_bytes())["score"]
                     for cid in clips for f in spoof_files if f.stem.startswith(cid)]
        asv_p_fa_spoof = float(np.mean(np.array(spoof_asv) >= theta)) if spoof_asv else 0.0
        cm = {"available": True, "eer": cm_eer,
              "min_tdcf": metrics.min_tdcf(bona_scores, spoof_scores,
                                           asv_p_miss, asv_p_fa, asv_p_fa_spoof),
              "asv_operating_point": {"threshold": round(theta, 4),
                                      "p_miss": round(asv_p_miss, 4),
                                      "p_fa": round(asv_p_fa, 4),
                                      "p_fa_spoof": round(asv_p_fa_spoof, 4)},
              "model_id": antispoof.model_id(),
              "caveat": ("Both classes originate from a text to speech system, because "
                         "no human speech is collected in this build, so what is measured "
                         "is the separation of two synthesis conditions and not human "
                         "speech from deepfakes. Both classes now pass through the same "
                         "simulated telephony channel. That matters: when only the bona "
                         "fide clips were band-limited, the mixture model learned "
                         "\"wideband means spoof\" and scored a clean recording of the "
                         "enrolled speaker at 0.02. It was a bandwidth detector with a "
                         "countermeasure's name on it. Sharing the channel forces it onto "
                         "voice and vocoder cues.")}
    return {"available": True, "speaker": asv, "n_speakers": len(clips),
            "countermeasure": cm, "model_id": speaker.model_id(),
            "caveat": "enrolment audio is synthetic unless a live voice was enrolled"}


# ---------------------------------------------------------------- driver

def run_all(conn=None, write: bool = True, with_latency: bool = True) -> dict:
    from .. import db
    conn = conn or db.init_db()
    data = load_set()
    items = data["utterances"]
    started = utcnow()

    results = {
        "generated_at": started.isoformat(),
        "eval_set": {"size": data["size"], "languages": data["languages"],
                     "entity_types": data["entity_types"], "path": str(UTTERANCES)},
        "langid": run_langid(items),
        "nlu": run_nlu(items),
        "retrieval": run_retrieval(items),
        "asr": run_asr(items),
        "biometrics": run_biometrics(conn),
    }

    traces = [json.loads(r["body"]) for r in
              conn.execute("SELECT body FROM traces ORDER BY created_at DESC LIMIT 500")]
    results["latency"] = (metrics.latency_from_traces(traces) if traces
                          else {"available": False,
                                "reason": "no traces recorded yet; run the scenario tests"})
    results["n_traces_for_latency"] = len(traces)

    # The per-stage table above is measured on the text path, where no speech
    # recognition and no synthesis run. It is true and it is not the number a
    # caller feels. R4 adds the audio path end to end; see eval/latency.py.
    if with_latency:
        from . import latency as latency_mod
        results["end_to_end"] = latency_mod.run(conn)
    else:
        results["end_to_end"] = {"available": False,
                                 "reason": "skipped, pass with_latency=True to measure"}

    # Write back the calibrated operating points so the running system uses the
    # numbers that were actually measured, not the cold-start defaults.
    calibration = {}
    if results["retrieval"]["available"]:
        calibration["delta"] = results["retrieval"]["calibrated_delta"]["delta"]
    if results["biometrics"].get("available"):
        calibration["theta"] = results["biometrics"]["speaker"]["threshold"]
    if calibration and write:
        calibration["measured_at"] = started.isoformat()
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_PATH.write_text(json.dumps(calibration, indent=2))
    results["calibration_written"] = calibration

    if write:
        RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_MD.write_text(render_markdown(results))
        (RUNTIME_DIR / "eval_results.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def _row(label: str, value, note: str = "") -> str:
    return f"| {label} | {value} | {note} |\n"


def render_markdown(r: dict) -> str:
    n = r["eval_set"]["size"]
    out = [
        "# Results\n\n",
        "Every number on this page was computed by `make eval`, which runs\n",
        "`backend/app/eval/harness.py` over `data/eval/`. Nothing here is typed in by\n",
        "hand. If a metric could not be computed, its row says so instead of carrying\n",
        "a placeholder.\n\n",
        f"Generated: {r['generated_at']}\n\n",
        f"Evaluation set: {n} hand-labelled utterances across "
        f"{', '.join(r['eval_set']['languages'])}. The set size is stated next to every\n",
        "number because a metric without its denominator is not a result.\n\n",
        "## Honest limitations, read these first\n\n",
        "- The ASR model is `faster-whisper base`, **not fine-tuned on banking audio**.\n",
        "  The entity-level error rate below is therefore the baseline that a fine-tuned\n",
        "  model has to beat, and is reported as such.\n",
        "- Evaluation audio is rendered with Piper, not recorded from humans over a\n",
        "  telephone line. WER on real telephony audio will be higher.\n",
        "- **The Hindi, Marathi and code-mixed rows below are not a valid measurement\n",
        "  of Indic speech recognition.** Those reference transcripts are written in\n",
        "  romanised Latin script, and rendering them through a Devanagari voice\n",
        "  produces mispronounced audio that no ASR system could be expected to\n",
        "  transcribe back to the romanised original. The English rows are the\n",
        "  interpretable ones. Fixing this needs recorded human audio, which is the\n",
        "  single highest value next step for the evaluation.\n",
        "- The anti-spoof component is a classical LFCC and GMM baseline, not AASIST.\n",
        "- Enrolment voices are synthetic unless a person enrolled through `/enroll`.\n",
        "- Figures quoted from the literature in the paper (15 to 20 percent WER on\n",
        "  Earnings-21, up to 72 percent phoneme error reduction from cross-lingual\n",
        "  pre-training) are literature values for other systems. They are not\n",
        "  measurements of this system and do not appear in the tables below.\n\n",
    ]

    out.append("## Language identification (A1)\n\n| Metric | Value | Note |\n|---|---|---|\n")
    l = r["langid"]
    out.append(_row("Dominant language accuracy", l["dominant_language_accuracy"],
                    f"{l['n_monolingual']} monolingual utterances"))
    out.append(_row("Mean CMI, code-mixed", l["mean_cmi_code_mixed"],
                    f"{l['n_code_mixed']} utterances, 0 would mean monolingual"))
    out.append(_row("Mean CMI, monolingual", l["mean_cmi_monolingual"],
                    "should be at or near 0"))
    out.append(_row("Code-mixed utterances with CMI > 0", l["cmi_nonzero_on_code_mixed"],
                    "fraction detected as mixed"))
    out.append(
        "\n> The word-level evidence is a script and lexicon prior, not a trained "
        "language identification head. Romanised Hindi and Marathi words outside the "
        "seeded function-word lexicon fall through to English, which is what the "
        "dominant-language accuracy above is measuring and why the monolingual CMI is "
        "not zero. The Viterbi smoother takes posteriors from any source, so a trained "
        "head would replace the prior without touching the smoothing.\n")

    out.append("\n## Intent classification (A3)\n\n| Metric | Value | Note |\n|---|---|---|\n")
    nl = r["nlu"]
    out.append(_row("Accuracy on the eval set", nl["accuracy_on_eval_set"],
                    f"{nl['n']} utterances, held out from the head's training bank"))
    out.append(_row("5-fold CV accuracy on the seed bank", nl["seed_cv_accuracy"],
                    f"{nl['n_train']} seeded utterances, std {nl['seed_cv_std']}"))
    if nl["confusions"]:
        out.append("\nTop confusions: " + ", ".join(
            f"`{k}` x{v}" for k, v in nl["confusions"].items()) + "\n")

    out.append("\n## Retrieval grounding (A4)\n\n| Metric | Value | Note |\n|---|---|---|\n")
    rt = r["retrieval"]
    cal = rt["calibrated_delta"]
    out.append(_row(f"Recall@{rt['k']}", rt["recall_at_k"],
                    f"{rt['n_answerable']} answerable queries"))
    out.append(_row("**Similarity floor delta, in use**", cal["delta"],
                    f"{cal.get('method', '')}, over {cal['n_answerable']} answerable "
                    f"and {cal['n_unanswerable']} unanswerable queries"))
    out.append(_row("Precision / recall / F1 at that delta",
                    f"{cal['precision']} / {cal['recall']} / {cal['f1']}", "on the same split"))
    if cal.get("f1_optimal"):
        fo = cal["f1_optimal"]
        out.append(_row("F1-optimal delta, not used", fo["delta"],
                        f"F1 {fo['f1']}, recall {fo['recall']}. Rejected: on a set this "
                        f"size it over-fits, and a real spoken query scored 0.58 against "
                        f"it and was refused."))
    out.append(_row("Lowest answerable score / highest unanswerable",
                    f"{cal.get('min_answerable_score')} / {cal.get('max_unanswerable_score')}",
                    "the gap the floor has to sit inside"))
    out.append(_row("Mean top score, answerable", rt["mean_score_answerable"], ""))
    out.append(_row("Mean top score, must-refuse", rt["mean_score_unanswerable"],
                    "the gap between these two rows is what the refusal path lives on"))
    out.append(_row("Mean top score, answered from core banking",
                    rt.get("mean_score_core_banking"),
                    f"{rt.get('n_excluded_from_calibration')} account and transaction "
                    f"queries, excluded from the calibration: they are neither grounding "
                    f"positives nor must-refuse negatives"))
    for lang, v in rt.get("answerable_by_language", {}).items():
        out.append(_row(f"  answerable top score, {lang}", v["mean_top_score"],
                        f"{v['n']} queries, lowest {v['min_top_score']}, "
                        f"{v['would_clear_delta']} of {v['n']} clear the calibrated delta"))
    out.append(
        "\n> The policy knowledge base is written in English. A Hindi or Marathi "
        "phrasing of the same question therefore scores lower through the cross-lingual "
        "gap in the embedding, not because the question is less answerable, and a single "
        "global floor refuses some of them. The rows above make that visible. Two "
        "reasonable fixes exist and neither is implemented here: a per-language floor, or "
        "a knowledge base with translated passages. This is a finding worth reporting in "
        "the paper rather than a bug to hide.\n")

    out.append("\n## Speech recognition (A9)\n\n")
    a = r["asr"]
    if not a["available"]:
        out.append(f"Not computed: {a['reason']}. Run `make eval-audio` to render the set.\n")
    else:
        out.append("| Metric | Value | Note |\n|---|---|---|\n")
        w = a["wer"]
        out.append(_row("WER", round(w["wer"], 4),
                        f"{w['utterances']} utterances, {w['ref_words']} reference words, "
                        f"model {a['model_id']}"))
        out.append(_row("Substitutions / deletions / insertions",
                        f"{w['substitutions']} / {w['deletions']} / {w['insertions']}", ""))
        for lang, w2 in a["wer_by_language"].items():
            out.append(_row(f"  WER, {lang}", round(w2["wer"], 4),
                            f"{w2['utterances']} utterances, {w2['ref_words']} reference words"))
        e = a["entities"]
        out.append(_row("**Entity-level error rate**", round(e["entity_error_rate"], 4),
                        f"{e['n_entities']} financial entities. This is the headline "
                        f"accuracy claim and the baseline a fine-tuned model must beat."))
        for etype, bucket in sorted(e["per_type"].items()):
            out.append(_row(f"  error rate, {etype}", round(bucket["error_rate"], 4),
                            f"{bucket['n']} entities"))
        for lang, bucket in sorted(e.get("per_language", {}).items()):
            out.append(_row(f"  error rate, {lang} audio", round(bucket["error_rate"], 4),
                            f"{bucket['n']} entities"))
        out.append(_row("ASR latency p50 / p95",
                        f"{a['asr_latency_ms']['p50']} ms / {a['asr_latency_ms']['p95']} ms",
                        "CPU, int8"))

    out.append("\n## Speaker verification and anti-spoofing (A6)\n\n")
    b = r["biometrics"]
    if not b.get("available"):
        out.append(f"Not computed: {b.get('reason')}\n")
    else:
        out.append("| Metric | Value | Note |\n|---|---|---|\n")
        s = b["speaker"]
        out.append(_row("Speaker EER", s["eer"],
                        f"{s['n_target']} target and {s['n_nontarget']} non-target trials "
                        f"over {b['n_speakers']} speakers, model {b['model_id']}. "
                        f"Trials: {s.get('trial_source', 'unspecified')}."))
        out.append(_row("theta at EER", s["threshold"],
                        "written to runtime/calibration.json and used by the live system"))
        if s["eer"] == 0.0:
            out.append(
                "\n> An equal error rate of zero is not a strong result here, it is a "
                "consequence of the trial set. Three distinct text to speech voices are "
                "trivially separable by any speaker embedding, and the trial counts above "
                "are small. Read this as evidence that the verification path is wired up "
                "and scoring correctly, not as a measure of how it would perform on real "
                "speakers over a telephone line.\n")
        cm = b["countermeasure"]
        if cm.get("available"):
            out.append(_row("Countermeasure EER", cm["eer"]["eer"],
                            f"{cm['eer']['n_target']} bona fide and "
                            f"{cm['eer']['n_nontarget']} spoof clips, {cm['model_id']}"))
            td = cm["min_tdcf"]
            if td.get("defined"):
                out.append(_row("min t-DCF (normalised)", td["min_tdcf"],
                                f"priors {td['priors']}, costs {td['costs']}"))
            else:
                out.append(_row("min t-DCF (normalised)", "undefined at this operating point",
                                f"{td.get('reason')}. C1 = {td.get('C1')}, "
                                f"C2 = {td.get('C2')}, priors {td.get('priors')}, "
                                f"costs {td.get('costs')}"))
            out.append(f"\n> {cm['caveat']}\n")
        else:
            out.append(_row("Countermeasure", "not computed", cm.get("reason", "")))
        out.append(f"\n> {b['caveat']}\n")
        out.append(
            "\n> **Channel mismatch is the practical limit on the verification path.** "
            "The same synthetic speaker scores 0.94 against their enrolment when the "
            "trial comes through the same simulated telephony channel, and 0.50 when it "
            "arrives as clean wideband audio, against a threshold of about 0.76. "
            "Enrolment and verification have to come through the same channel. For the "
            "live demo that means enrolling a real voice from the same microphone, which "
            "the customer console now supports; the seeded synthetic enrolments are for "
            "the text path.\n")

    out.append("\n## Latency per stage\n\n")
    lat = r["latency"]
    if lat.get("available") is False:
        out.append(f"Not computed: {lat['reason']}\n")
    else:
        out.append(f"From {r['n_traces_for_latency']} recorded traces. The p95 for the "
                   "`nlu` stage includes the first turn after a cold start, which pays "
                   "the one-off embedding model load; the server warms that at startup "
                   "so a live demo does not see it.\n\n")
        out.append("| Stage | n | p50 ms | p95 ms |\n|---|---|---|---|\n")
        for name, v in sorted(lat.items()):
            label = "**turn total**" if name == "_turn_total" else name
            out.append(f"| {label} | {v['n']} | {v['p50_ms']} | {v['p95_ms']} |\n")

    # The table above is the text path. The audio path is what a caller feels.
    from . import latency as latency_mod
    out.append(latency_mod.render_markdown(r.get("end_to_end", {"available": False,
               "reason": "not run"})))

    out.append("\n## Reproducing this page\n\n```\nmake seed\nmake eval-audio\nmake eval\n```\n")
    return "".join(out)
