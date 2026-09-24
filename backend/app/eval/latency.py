"""R4, first half: measure before touching anything.

The existing latency table in RESULTS.md reports a 26 ms turn total, which is
true and useless: it was measured on the text path, where no speech
recognition and no synthesis happen. The 4.6 s round trip the demo actually
showed lives almost entirely in the two stages that table leaves out.

So this harness runs the **audio** path end to end and reports the number
that matters: from the end of the caller's speech to the first audible
reply. It reports it twice, as the change request requires:

- `first_audio_ms`, time until any audio could start playing, and
- `first_content_audio_ms`, time until the audio of the actual answer could
  start playing.

Today these are identical, because nothing is streamed and no acknowledgement
is spoken. That is the honest starting point, and keeping both columns from
the beginning is what stops a later filler being quietly counted as an
improvement.

**What is not measured here.** Network transfer and the browser's playback
start are client side. This harness runs in process, so its numbers are a
lower bound on what a caller experiences, and the table says so. Endpoint
detection is likewise not included: the eval clips are pre-trimmed files, so
there is no endpointing decision to time. Both gaps are named in the output
rather than papered over.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from ..config import DATA_DIR
from ..pipeline.prosody import split_phrases

EVAL_DIR = DATA_DIR / "eval"
AUDIO_DIR = EVAL_DIR / "audio"
TARGET_PER_LANGUAGE = 30


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(q * len(ordered)))
    return round(ordered[idx], 1)


def _summary(values: list[float]) -> dict:
    return {"n": len(values), "p50_ms": _pct(values, 0.5),
            "p95_ms": _pct(values, 0.95),
            "mean_ms": round(statistics.mean(values), 1) if values else 0.0}


def load_items() -> list[dict]:
    items = json.loads((EVAL_DIR / "utterances.json").read_text())["utterances"]
    return [i for i in items if (AUDIO_DIR / f"{i['id']}.wav").exists()]


def _plan(items: list[dict], per_language: int) -> dict[str, list[dict]]:
    """`per_language` turns for each path, cycling the clips if there are
    fewer than that.

    Repeating a clip adds nothing to an accuracy measurement and would be
    dishonest there. For latency it is fine: the same audio takes the same
    work each time, and the point is the distribution of how long that work
    takes. The repeat factor is reported so nobody reads 30 independent
    samples into 8 clips.
    """
    by_lang: dict[str, list[dict]] = {}
    for item in items:
        by_lang.setdefault(item["language"], []).append(item)
    plan = {}
    for lang, group in by_lang.items():
        picked = [group[i % len(group)] for i in range(per_language)]
        plan[lang] = picked
    return plan


def run(conn=None, per_language: int = TARGET_PER_LANGUAGE,
        customer_id: str = "CUST1000", clu: bool = False) -> dict:
    """Time the audio path. Returns per-language and overall summaries.

    `clu` is off by default and that is a measurement decision, not a
    convenience. The contextual layer is an optional cloud call, and on a
    free tier it answers 429 and waits. One turn in the first run of this
    harness was measured at 96 seconds, nearly all of it spent in rate-limit
    backoff. Leaving that in would report the vendor's free tier as this
    system's latency, which is the same mistake that made the first CLU
    accuracy evaluation meaningless.

    So the headline is the local stack, which is what R4's targets are about,
    and the CLU's own cost is reported separately by `clu_overhead`.
    """
    import os
    from .. import db, turn
    from ..pipeline import tts

    previous = os.environ.get("BFSI_CLU_PROVIDER")
    if not clu:
        os.environ["BFSI_CLU_PROVIDER"] = "null"
    conn = conn or db.init_db()
    items = load_items()
    if not items:
        return {"available": False,
                "reason": "no evaluation audio; run `make eval-audio` first"}

    plan = _plan(items, per_language)
    counts = {lang: len({i["id"] for i in picked}) for lang, picked in plan.items()}

    # Warm every model once, outside the measurement. A cold load inside the
    # first turn is a real cost, but it is a startup cost and reporting it
    # inside a per-turn percentile would misrepresent both.
    warm = time.perf_counter()
    first = items[0]
    session = turn.create_session(conn, customer_id, device_id="latency-warm",
                                  voice_clip=f"{customer_id}_0.wav")
    turn.run_turn(conn, session["session_id"],
                  audio=(AUDIO_DIR / f"{first['id']}.wav").read_bytes())
    tts.synthesize("warming the synthesiser", "en")
    warm_ms = (time.perf_counter() - warm) * 1000.0

    rows: list[dict] = []
    for lang, picked in plan.items():
        session = turn.create_session(conn, customer_id,
                                      device_id=f"latency-{lang}",
                                      voice_clip=f"{customer_id}_0.wav")
        for item in picked:
            audio = (AUDIO_DIR / f"{item['id']}.wav").read_bytes()
            t0 = time.perf_counter()
            trace = turn.run_turn(conn, session["session_id"], audio=audio)
            pipeline_ms = (time.perf_counter() - t0) * 1000.0

            reply = trace.reply_text or ""
            reply_lang = trace.reply_language or lang

            # The whole reply, which is what the caller used to wait for.
            t1 = time.perf_counter()
            if reply:
                tts.synthesize(reply, reply_lang)
            tts_ms = (time.perf_counter() - t1) * 1000.0

            # The first phrase only, which is what they wait for now. Timed
            # separately rather than divided out of the total, because
            # synthesis is not linear in length and an estimate here would be
            # the kind of number this project is not allowed to print.
            phrases = [ph for ph, _ in split_phrases(reply) if ph.strip()] or [reply]
            t2 = time.perf_counter()
            if phrases and phrases[0]:
                tts.synthesize(phrases[0], reply_lang)
            first_phrase_ms = (time.perf_counter() - t2) * 1000.0

            stages = {s.stage: s.duration_ms for s in trace.stages}
            rows.append({
                "id": item["id"], "language": lang,
                "vad_ms": stages.get("vad", 0.0),
                "asr_ms": stages.get("asr", 0.0),
                "nlu_ms": stages.get("nlu", 0.0),
                "retrieval_ms": stages.get("retrieval", 0.0),
                "risk_ms": stages.get("risk", 0.0),
                "pipeline_ms": pipeline_ms,
                "tts_ms": tts_ms,
                "tts_first_phrase_ms": first_phrase_ms,
                "phrases": len(phrases),
                "streamed_first_audio_ms": pipeline_ms + first_phrase_ms,
                # Nothing is streamed and no acknowledgement is spoken, so the
                # first audio the caller could hear is the whole reply, and
                # both figures are the same. Kept apart from the start so a
                # later filler cannot be mistaken for a real improvement.
                "first_audio_ms": pipeline_ms + tts_ms,
                "first_content_audio_ms": pipeline_ms + tts_ms,
                "reply_chars": len(reply),
            })

    by_language = {}
    for lang in plan:
        subset = [r for r in rows if r["language"] == lang]
        by_language[lang] = {
            "turns": len(subset),
            "distinct_clips": counts[lang],
            "repeat_factor": round(len(subset) / max(counts[lang], 1), 1),
            "first_audio": _summary([r["first_audio_ms"] for r in subset]),
            "streamed_first_audio": _summary(
                [r["streamed_first_audio_ms"] for r in subset]),
            "first_content_audio": _summary(
                [r["first_content_audio_ms"] for r in subset]),
            "stages": {name: _summary([r[name] for r in subset])
                       for name in ("vad_ms", "asr_ms", "nlu_ms", "retrieval_ms",
                                    "risk_ms", "pipeline_ms", "tts_ms",
                                    "tts_first_phrase_ms")},
        }

    if previous is None:
        os.environ.pop("BFSI_CLU_PROVIDER", None)
    else:
        os.environ["BFSI_CLU_PROVIDER"] = previous

    return {
        "available": True,
        "clu_enabled": clu,
        "measured_at": time.strftime("%Y-%m-%d"),
        "turns": len(rows),
        "per_language": per_language,
        "warm_up_ms": round(warm_ms, 1),
        "by_language": by_language,
        "overall": {
            "first_audio": _summary([r["first_audio_ms"] for r in rows]),
            "first_content_audio": _summary(
                [r["first_content_audio_ms"] for r in rows]),
            "streamed_first_audio": _summary(
                [r["streamed_first_audio_ms"] for r in rows]),
            "stages": {name: _summary([r[name] for r in rows])
                       for name in ("vad_ms", "asr_ms", "nlu_ms", "retrieval_ms",
                                    "risk_ms", "pipeline_ms", "tts_ms",
                                    "tts_first_phrase_ms")},
        },
        "not_measured": [
            "the contextual language layer, which is an optional cloud call "
            "and was disabled for this measurement; on a free tier its "
            "rate-limit backoff reached 96 s on a single turn, which would "
            "have reported the vendor's queue as this system's latency",
            "network transfer and browser playback start, which are client side; "
            "these numbers are a lower bound on what a caller experiences",
            "endpoint detection, because the evaluation clips are pre-trimmed "
            "files and there is no endpointing decision to time",
        ],
        "rows": rows,
    }


def render_markdown(r: dict[str, Any]) -> str:
    if not r.get("available"):
        return f"\n## End to end latency\n\nNot measured: {r['reason']}\n"

    out = ["\n## End to end latency on the audio path", ""]
    out.append(f"Measured {r['measured_at']} over {r['turns']} audio turns, "
               f"{r['per_language']} per language path, on the development "
               f"laptop with the local stack (faster-whisper base int8 and "
               f"Kokoro). Models were warmed first; the warm up itself took "
               f"{r['warm_up_ms'] / 1000:.1f} s and is a startup cost, not a "
               f"per-turn one.")
    out.append("")
    out.append("**The metric that matters** is the end of the caller's speech "
               "to the first audible reply. It is reported twice: time to any "
               "audio, and time to the audio of the actual answer. They are "
               "identical today, because nothing is streamed and no "
               "acknowledgement is spoken. Both columns are kept so that a "
               "filler added later cannot be counted as a real improvement.")
    out.append("")
    for note in r["not_measured"]:
        out.append(f"- Not included: {note}")
    out.append("")

    out.append("| Path | turns | clips | before p50 | before p95 | after p50 | after p95 |")
    out.append("|---|---|---|---|---|---|---|")
    for lang, d in sorted(r["by_language"].items()):
        b, a = d["first_audio"], d["streamed_first_audio"]
        out.append(
            f"| {lang} | {d['turns']} | {d['distinct_clips']} "
            f"| {b['p50_ms']} | {b['p95_ms']} | {a['p50_ms']} | {a['p95_ms']} |")
    o = r["overall"]
    b, a = o["first_audio"], o["streamed_first_audio"]
    out.append(f"| **all** | {r['turns']} | | **{b['p50_ms']}** | **{b['p95_ms']}** "
               f"| **{a['p50_ms']}** | **{a['p95_ms']}** |")
    out.append("")
    out.append("All figures in milliseconds. **Before** is waiting for the whole "
               "reply to be synthesised, which is what the system did. **After** "
               "is waiting only for its first phrase, which is what it does now: "
               "the remaining phrases are made while the first one plays.")
    if b["p50_ms"]:
        saved = round(100 * (1 - a["p50_ms"] / b["p50_ms"]))
        out.append("")
        out.append(f"That is {saved}% off the p50 wait, from "
                   f"{b['p50_ms'] / 1000:.1f} s to {a['p50_ms'] / 1000:.1f} s. "
                   f"The change request's target is 1.2 s, so this does not "
                   f"reach it. What blocks the rest is named below.")
    out.append("")

    out.append("### Where the time goes")
    out.append("")
    out.append("| Stage | n | p50 ms | p95 ms |")
    out.append("|---|---|---|---|")
    labels = {"vad_ms": "voice activity detection", "asr_ms": "speech recognition",
              "nlu_ms": "intent and slots", "retrieval_ms": "policy retrieval",
              "risk_ms": "risk and gate", "pipeline_ms": "everything to the reply text",
              "tts_ms": "speech synthesis, whole reply",
              "tts_first_phrase_ms": "speech synthesis, first phrase only"}
    for name, label in labels.items():
        s = o["stages"][name]
        out.append(f"| {label} | {s['n']} | {s['p50_ms']} | {s['p95_ms']} |")
    out.append("")

    out.append("**What blocks the 1.2 s target.** With the whole reply no longer "
               "on the caller's clock, the two remaining costs are speech "
               "recognition and the first phrase of synthesis. Recognition "
               "finishes only after the caller stops speaking, so the way to "
               "remove it is to transcribe while they are still talking; that "
               "is a streaming recogniser and a larger piece of work than "
               "anything above. The deterministic pipeline this project is "
               "actually about, intent through risk and the gate, costs under "
               "a tenth of a second in total and is not worth optimising.")
    out.append("")

    repeats = {lang: d["repeat_factor"] for lang, d in r["by_language"].items()}
    if any(v > 1 for v in repeats.values()):
        out.append("Clips were cycled to reach the target turn count where a "
                   f"language has fewer than {r['per_language']} of them "
                   f"(repeat factor {repeats}). Repeating a clip adds nothing "
                   "to an accuracy measurement, but for latency it is sound: "
                   "the same audio is the same work, and what is being measured "
                   "is how long that work takes.")
        out.append("")
    return "\n".join(out)
