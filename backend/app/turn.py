"""The turn orchestrator: one ComplianceTrace threaded through every stage.

This is where the paper's central claim either holds or does not. Every stage
below opens `trace.stage(...)`, writes what it produced into the record, and
hands the trace on. Nothing influences the outcome without passing through
here, and at the end the trace is redacted, hashed and appended to the ledger.

Order is deliberate:

    consent -> [vad -> asr] -> langid -> nlu -> retrieval -> fusion
            -> anomalies -> auth -> risk -> tier -> gate -> action
            -> reply -> tts -> redact -> persist -> ledger

PII redaction sits between reply and persist, not earlier, because slot
extraction genuinely needs the digits. Nothing between those two points writes
to disk.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .banking import actions
from .banking.mock_core import MockCore
from .config import (GROUNDED_INTENTS, OTP_DEMO_CODE, TIER_REQUIRING_OTP,
                     TIER_REQUIRING_VERIFICATION, VERIFICATION_MAX_TURNS,
                     VERIFICATION_TTL_SECONDS)
from . import clu
from .pipeline import dialogue, langid, nlu, retrieval
from .security import crypto, ledger, pii
from .trace import AuthOutcome, ComplianceTrace, utcnow

# Per-session working state that is not worth a table: the pending tier 2
# action awaiting OTP and read-back, and the last verification outcome.
SESSION_STATE: dict[str, dict] = {}


def state(session_id: str) -> dict:
    return SESSION_STATE.setdefault(session_id, {
        "pending": None, "auth": None, "pii_counters": {}, "pii_seen": {},
        "recent_turns": [],
    })


# ---------------------------------------------------------------- sessions

def create_session(conn: sqlite3.Connection, customer_id: str | None,
                   device_id: str | None = None, voice_clip: str | None = None,
                   languages: str = "en,hi,mr") -> dict:
    """Open a session and record consent as the first ledger entry of the call."""
    from .config import CONSENT_PURPOSE, CONSENT_RETENTION_DAYS
    session_id, consent_ref = str(uuid.uuid4()), str(uuid.uuid4())
    now = utcnow().isoformat()
    conn.execute(
        "INSERT INTO sessions (session_id, customer_id, consent_ref, created_at,"
        " device_id, voice_clip) VALUES (?,?,?,?,?,?)",
        (session_id, customer_id, consent_ref, now, device_id, voice_clip))
    conn.execute(
        "INSERT INTO consents (consent_ref, session_id, purpose, retention_days,"
        " granted_at, languages) VALUES (?,?,?,?,?,?)",
        (consent_ref, session_id, CONSENT_PURPOSE, CONSENT_RETENTION_DAYS, now, languages))
    conn.commit()
    record = ledger.append(conn, "consent", {
        "session_id": session_id, "consent_ref": consent_ref,
        "purpose": CONSENT_PURPOSE, "retention_days": CONSENT_RETENTION_DAYS,
        "languages": languages, "granted_at": now,
        "customer_ref": customer_id, "notice_spoken": True,
    }, session_id=session_id)
    return {"session_id": session_id, "consent_ref": consent_ref,
            "purpose": CONSENT_PURPOSE, "retention_days": CONSENT_RETENTION_DAYS,
            "ledger_index": record["idx"], "ledger_hash": record["hash"],
            "consent_notice": consent_notice(languages)}


def consent_notice(languages: str = "en") -> dict[str, str]:
    from .config import CONSENT_RETENTION_DAYS
    return {
        "en": ("Before we begin. This call is handled by an automated assistant. Your "
               f"voice is processed to understand your request and is kept for "
               f"{CONSENT_RETENTION_DAYS} days for audit purposes. Identifiers are masked "
               "before anything is stored, and you can ask for a human agent at any point. "
               "Say yes to continue."),
        "hi": ("शुरू करने से पहले एक बात। यह कॉल एक स्वचालित सहायक संभाल रहा है। आपकी आवाज़ "
               "आपकी बात समझने के लिए संसाधित की जाती है और ऑडिट के लिए "
               f"{CONSENT_RETENTION_DAYS} दिन रखी जाती है। कुछ भी सहेजने से पहले पहचान छिपा दी "
               "जाती है, और आप कभी भी किसी व्यक्ति से बात माँग सकते हैं। जारी रखने के लिए हाँ कहिए।"),
        "mr": ("सुरुवात करण्यापूर्वी एक गोष्ट. हा कॉल एक स्वयंचलित सहाय्यक हाताळत आहे. तुमचा आवाज "
               "तुमची विनंती समजून घेण्यासाठी प्रक्रिया केला जातो आणि ऑडिटसाठी "
               f"{CONSENT_RETENTION_DAYS} दिवस ठेवला जातो. काहीही साठवण्यापूर्वी ओळख लपवली "
               "जाते, आणि तुम्ही कधीही माणसाशी बोलण्याची मागणी करू शकता. पुढे जाण्यासाठी होय म्हणा."),
    }


def get_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        raise KeyError(f"unknown session {session_id}")
    if row["withdrawn_at"]:
        raise PermissionError("consent for this session has been withdrawn")
    return row


# ---------------------------------------------------------------- anomalies

def detect_anomalies(conn: sqlite3.Connection, session: sqlite3.Row, slots: dict) -> list[str]:
    """dev(history) inputs. Each one is a named string so the dashboard can
    list exactly which anomalies fired rather than showing a bare count."""
    found: list[str] = []
    st = state(session["session_id"])

    if session["device_id"]:
        prior = conn.execute(
            "SELECT COUNT(*) c FROM sessions WHERE customer_id=? AND device_id=?"
            " AND session_id<>?",
            (session["customer_id"], session["device_id"], session["session_id"])).fetchone()
        if prior["c"] == 0:
            found.append("new_device")

    hour = datetime.now(timezone.utc).astimezone().hour
    if hour < 6 or hour >= 22:
        found.append("unusual_hour")

    payee = slots.get("payee")
    if payee and session["customer_id"]:
        known = {p["name"].lower() for p in MockCore(conn).get_payees(session["customer_id"])}
        if payee.lower() not in known:
            found.append("first_ever_payee")

    now = utcnow().timestamp()
    st["recent_turns"] = [t for t in st["recent_turns"] if now - t < 60]
    if len(st["recent_turns"]) >= 3:
        found.append("rapid_repeat_attempts")
    st["recent_turns"].append(now)
    return found


# ---------------------------------------------------------------- the turn

def run_turn(conn: sqlite3.Connection, session_id: str, *, text: str | None = None,
             audio: bytes | None = None, otp: str | None = None,
             confirm: bool | None = None, asr_confidence: float | None = None,
             agent_id: str | None = None) -> ComplianceTrace:
    session = get_session(conn, session_id)
    st = state(session_id)
    turn_index = session["turn_count"]
    trace = ComplianceTrace(session_id=uuid.UUID(session_id), turn_index=turn_index,
                            consent_ref=uuid.UUID(session["consent_ref"]))
    core = MockCore(conn)

    # ---------------------------------------------------------- 1. transcript
    if audio is not None:
        from .pipeline import asr, vad
        with trace.stage("vad", audio, component="vad") as rec:
            speech = vad.trim_to_speech(audio)
            rec.outputs = speech["summary"]
            rec.model_id = speech["model_id"]
        with trace.stage("asr", speech["audio"], component="asr") as rec:
            out = asr.transcribe(speech["audio"])
            text = out["text"]
            rec.outputs = {"text_length": len(text), "segments": out["n_segments"],
                           "detected_language": out["language"],
                           "avg_logprob": out["avg_logprob"]}
            rec.confidence = out["confidence"]
            rec.model_id = out["model_id"]
            asr_confidence = out["confidence"]
        del speech        # raw audio is dropped as soon as the text exists
    else:
        with trace.stage("text_input", text or "", component="asr") as rec:
            rec.outputs = {"length": len(text or ""), "mode": "text_fallback"}
            rec.confidence = asr_confidence if asr_confidence is not None else 0.99
            rec.model_id = "text-fallback"
            rec.notes = ("typed input, no ASR ran; the pipeline below is identical to "
                         "the voice path")
        if asr_confidence is None:
            asr_confidence = 0.99

    text = text or ""
    trace.transcript = text
    trace.asr_confidence = float(asr_confidence)

    # ---------------------------------------------------------- 2. language id
    with trace.stage("langid", text, component="langid") as rec:
        lid = langid.identify(text)
        trace.language_spans = lid["spans"]
        trace.code_mix_index = lid["code_mix_index"]
        trace.dominant_language = lid["dominant"]
        rec.outputs = {"spans": [s.model_dump() for s in lid["spans"]],
                       "code_mix_index": lid["code_mix_index"],
                       "dominant": lid["dominant"], "counts": lid["counts"],
                       "eta": lid["eta"]}
        rec.confidence = (sum(s.confidence for s in lid["spans"]) / len(lid["spans"])
                          if lid["spans"] else 0.0)
        rec.model_id = f"viterbi-langid/eta={lid['eta']}"

    lang = trace.dominant_language or "en"

    # ---------------------------------------------------------- 3. resume a pending action
    pending = st.get("pending")
    if pending and (otp is not None or confirm is not None):
        return _resume_pending(conn, session, trace, pending, otp, confirm, lang, core)

    # ---------------------------------------------------------- 4. NLU
    # The deterministic head runs on every turn, always, whether or not the
    # language layer is enabled. It is the floor the CLU cannot go under.
    with trace.stage("nlu", text, component="nlu") as rec:
        understanding = nlu.understand(text)
        trace.intent = understanding["intent"]
        trace.intent_confidence = understanding["confidence"]
        trace.slots = understanding["slots"]
        rec.outputs = {"intent": understanding["intent"], "ranking": understanding["ranking"],
                       "margin": round(understanding["margin"], 4),
                       "slots": understanding["slots"]}
        rec.confidence = understanding["confidence"]
        rec.model_id = understanding["model_id"]

    # ---------------------------------------------------------- 4b. CLU
    # Optional. Reads the turn for code-mixing, compound asks and references
    # to earlier turns. Decides nothing: the merge below refuses to let it
    # lower the assessed risk of a turn.
    if clu.enabled():
        with trace.stage("clu", {"transcript_len": len(text),
                                 "baseline_intent": understanding["intent"]},
                         component="clu") as rec:
            outcome = clu.understand_turn(
                text, context=_conversation_context(conn, session),
                baseline_confidence=understanding["confidence"],
                baseline_margin=understanding["margin"],
                code_mix_index=trace.code_mix_index or 0.0)
            merged = clu.merge_with_baseline(
                understanding["intent"], understanding["confidence"],
                understanding["slots"], outcome)
            rec.outputs = outcome.to_trace() | {
                "merged_intent": merged["intent"], "decision_source": merged["source"],
                "override_blocked": merged["override_blocked"],
                "override_reason": merged["override_reason"],
                "baseline_intent": understanding["intent"],
                "baseline_confidence": round(understanding["confidence"], 4),
            }
            rec.confidence = merged["confidence"]
            rec.model_id = f"{outcome.provider}/{outcome.model}@{outcome.prompt_version}"
            rec.notes = ("data left this machine for this turn"
                         if outcome.leaves_machine and outcome.called else None)
            trace.intent = merged["intent"]
            trace.intent_confidence = merged["confidence"]
            trace.slots = merged["slots"]
            trace.clu_source = merged["source"]
            trace.sub_intents = merged["sub_intents"]
            trace.references = merged["references"]
            trace.normalized_text = merged["normalized_text"]

    # ---------------------------------------------------------- 5. retrieval
    grounding_required = dialogue.needs_grounding(trace.intent)
    c_retr: float | None = None
    if dialogue.runs_retrieval(trace.intent):
        with trace.stage("retrieval", {"query": text, "intent": trace.intent},
                         component="retrieval") as rec:
            found = retrieval.search(text)
            trace.retrieved = found["passages"]
            trace.retrieval_max_score = found["max_score"]
            trace.retrieval_floor = found["floor"]
            c_retr = min(1.0, found["max_score"] / found["floor"]) if found["floor"] else 1.0
            c_retr = max(0.0, min(1.0, found["max_score"]))
            rec.outputs = {"n_passages": len(found["passages"]),
                           "max_score": found["max_score"], "floor": found["floor"],
                           "grounded": found["grounded"],
                           "citations": [{"doc_id": p.doc_id, "version": p.version,
                                          "section": p.section, "score": p.score}
                                         for p in found["passages"]],
                           "superseded_versions": [{"doc_id": p.doc_id, "version": p.version}
                                                   for p in found["superseded"]],
                           "n_candidates": found["n_candidates"]}
            rec.confidence = c_retr
            rec.model_id = found["model_id"]
    grounded = bool(trace.retrieved)
    trace.retrieval_confidence = c_retr

    # ---------------------------------------------------------- 6. confidence fusion
    with trace.stage("fusion", {"c_asr": trace.asr_confidence,
                                "c_intent": trace.intent_confidence,
                                "c_retr": c_retr}, component="nlu") as rec:
        fused = dialogue.fuse_confidence(trace.asr_confidence, trace.intent_confidence, c_retr)
        trace.fused_confidence = fused["c_final"]
        trace.fusion_weights = {k: fused[k] for k in ("alpha", "beta", "gamma")}
        rec.outputs = fused
        rec.confidence = fused["c_final"]
        rec.model_id = "geometric-fusion"

    # ---------------------------------------------------------- 7. anomalies
    with trace.stage("anomaly", trace.slots, component="core_banking") as rec:
        anomalies = detect_anomalies(conn, session, trace.slots)
        rec.outputs = {"anomalies": anomalies, "count": len(anomalies)}
        rec.model_id = "rule-based"

    # ---------------------------------------------------------- 8. provisional tier
    # The tier decides whether verification is needed, and verification feeds
    # the score, so the score is computed twice: once with s_verify unknown to
    # pick the tier, then again with the measured value. Both are in the trace.
    provisional_R, provisional_components = dialogue.risk_score(
        trace.intent, trace.slots.get("amount"), st.get("auth", {}).get("s_verify")
        if st.get("auth") else None, anomalies)
    provisional = dialogue.assign_tier(provisional_R, trace.intent, session["tier_floor"])

    # ---------------------------------------------------------- 9. authentication
    auth = _authenticate(conn, session, trace, provisional["tier"], audio, st)

    # ---------------------------------------------------------- 10. final risk and tier
    with trace.stage("risk", {"intent": trace.intent, "slots": trace.slots,
                              "anomalies": anomalies,
                              "s_verify": auth.s_verify if auth else None},
                     component="nlu") as rec:
        R, components = dialogue.risk_score(
            trace.intent, trace.slots.get("amount"),
            auth.s_verify if auth else None, anomalies)
        tiering = dialogue.assign_tier(R, trace.intent, session["tier_floor"])
        trace.risk_score = float(R)   # unrounded: the recompute test compares exactly
        trace.risk_tier = tiering["tier"]
        trace.risk_components = components | {"provisional_R": float(provisional_R),
                                              "tiering": tiering}
        trace.tier_overridden = tiering["overridden"]
        trace.tier_ratcheted = tiering["ratcheted"]
        trace.tau_required = dialogue.tau_for(tiering["tier"])
        rec.outputs = {"R": trace.risk_score, "tier": trace.risk_tier,
                       "components": components, "tiering": tiering}
        rec.confidence = None
        rec.model_id = "weighted-linear-risk"

    # The ratchet is persisted so it survives a reconnect, but it only moves on
    # a CONFIDENT escalation, and it decays on clean turns. Without both guards
    # one garbled transcript pins the session at tier 3 for the rest of the
    # call; see config.RATCHET_* and tests/test_ratchet.py.
    _update_ratchet(conn, session, trace, tiering)

    # ---------------------------------------------------------- 11. the gate
    otp_needed = trace.risk_tier >= TIER_REQUIRING_OTP
    with trace.stage("policy", {"tier": trace.risk_tier, "R": trace.risk_score,
                                "c_final": trace.fused_confidence}, component="nlu") as rec:
        verdict = dialogue.gate(
            tier=trace.risk_tier, R=R, c_final=trace.fused_confidence or 0.0,
            needs_grounding=grounding_required, grounded=grounded,
            verification_passed=auth.passed if auth else None,
            otp_passed=None if otp_needed else True,
            readback_confirmed=None if otp_needed else True)
        rec.outputs = verdict
        rec.model_id = "tier-gate"

    # ---------------------------------------------------------- 12. act
    outcome = _act(conn, session, trace, verdict, auth, otp_needed, lang, core, st)
    trace.decision = outcome["decision"]
    trace.decision_reason = outcome["reason"]
    trace.action_taken = outcome["action_taken"]
    trace.action_result = outcome["result"]
    trace.reply_text = outcome["reply"]
    trace.reply_language = lang
    trace.agent_id = agent_id

    # ---------------------------------------------------------- 13. redact and persist
    finalise(conn, session, trace)
    conn.execute("UPDATE sessions SET turn_count=turn_count+1 WHERE session_id=?",
                 (session["session_id"],))
    conn.commit()
    return trace


# ---------------------------------------------------------------- helpers

def _conversation_context(conn: sqlite3.Connection, session: sqlite3.Row) -> list[dict]:
    """A bounded slice of the session so far, for reference resolution.

    Redacted transcripts only, and only the last few turns. Sending an
    unbounded history to a model would be a cost problem and, with a hosted
    provider, a disclosure problem.
    """
    import json as _json
    from .config import CLU_CONTEXT_TURNS
    rows = conn.execute(
        "SELECT body FROM traces WHERE session_id=? ORDER BY turn_index DESC LIMIT ?",
        (session["session_id"], CLU_CONTEXT_TURNS)).fetchall()
    out = []
    for r in reversed(rows):
        b = _json.loads(r["body"])
        out.append({"transcript": b.get("transcript"), "intent": b.get("intent"),
                    "action": b.get("action_taken")})
    return out


def _update_ratchet(conn: sqlite3.Connection, session: sqlite3.Row,
                    trace: ComplianceTrace, tiering: dict) -> None:
    """Move the session floor up on a confident escalation, down on clean turns."""
    from .config import RATCHET_DECAY_AFTER_CLEAN_TURNS

    from .config import NON_RATCHETING_TIER3

    floor = session["tier_floor"]
    clean = session["clean_turns"]
    raised = dialogue.ratchet_should_raise(
        trace.intent, trace.intent_confidence, trace.risk_tier, floor)
    if raised and trace.intent in NON_RATCHETING_TIER3:
        # Escalate the turn, leave the call alone. Wanting a human or wanting
        # advice is not evidence that anything is wrong with the account.
        raised = False
        clean += 1
        conn.execute("UPDATE sessions SET clean_turns=? WHERE session_id=?",
                     (clean, session["session_id"]))
        conn.commit()
        trace.risk_components["ratchet"] = {
            "floor_before": floor, "floor_after": floor, "clean_turns": clean,
            "raised": False,
            "note": f"{trace.intent} escalates the turn but does not raise the session "
                    f"floor: it is outside what the assistant may answer, not a risk signal",
            "applies_to_this_intent": tiering.get("ratchet_applies"),
        }
        return

    if raised:
        floor, clean = trace.risk_tier, 0
        note = f"floor raised to {floor} on a confident escalation"
    elif trace.risk_tier > session["tier_floor"]:
        # Escalated, but we were not sure what we heard. Escalate the turn and
        # leave the session alone rather than ruining the rest of the call.
        clean = 0
        note = (f"turn escalated to tier {trace.risk_tier} but intent confidence "
                f"{trace.intent_confidence:.2f} is below the ratchet threshold, "
                f"so the session floor stays at {floor}")
    else:
        clean += 1
        if floor > 0 and clean >= RATCHET_DECAY_AFTER_CLEAN_TURNS:
            floor, clean = floor - 1, 0
            note = f"floor decayed to {floor} after {RATCHET_DECAY_AFTER_CLEAN_TURNS} clean turns"
        else:
            note = f"floor held at {floor}, {clean} clean turn(s)"

    conn.execute("UPDATE sessions SET tier_floor=?, clean_turns=? WHERE session_id=?",
                 (floor, clean, session["session_id"]))
    conn.commit()
    trace.risk_components["ratchet"] = {
        "floor_before": session["tier_floor"], "floor_after": floor,
        "clean_turns": clean, "raised": raised, "note": note,
        "applies_to_this_intent": tiering.get("ratchet_applies"),
    }


def record_verification(conn: sqlite3.Connection, session_id: str,
                        audio: bytes | None = None, source: str = "live") -> dict:
    """Run a voice check and store the outcome on the session.

    This is the only thing that produces a verification. A turn consumes the
    stored result while it is fresh; it never re-scores a file on disk and
    calls that a check.

    `source="demo_clip"` runs the check against the seeded clip attached to
    the session instead of live audio. That exists so the runbook survives a
    dead microphone, and it is recorded as SIMULATED everywhere it appears:
    in the trace stage, in the ledger record and on the dashboard. It is a
    demonstration of the mechanism, not evidence about who is speaking.
    """
    from .security import antispoof, speaker
    session = get_session(conn, session_id)
    if not session["customer_id"]:
        return {"passed": False, "reason": "session has no customer"}

    if audio is None:
        if source != "demo_clip" or not session["voice_clip"]:
            return {"passed": False, "reason": "no audio and no demo clip on this session"}
        try:
            audio = speaker.load_clip(session["voice_clip"])
        except FileNotFoundError:
            return {"passed": False, "simulated": True,
                    "reason": f"no seeded clip {session['voice_clip']} exists for this "
                              f"customer; only the three seeded voices have one. "
                              f"Enrol a real voice instead."}
    result = speaker.verify(conn, session["customer_id"], audio)
    spoof = antispoof.score(audio)
    s_verify = result["score"] * spoof["score"]
    passed = bool(result["score"] >= result["threshold"] and spoof["bona_fide"])
    now = utcnow()
    conn.execute(
        "UPDATE sessions SET verified_at=?, verified_score=?, verified_spoof=?,"
        " verified_source=?, verified_turns=0 WHERE session_id=?",
        (now.isoformat() if passed else None, result["score"], spoof["score"],
         source, session_id))
    conn.commit()
    ledger.append(conn, "verification", {
        "session_id": session_id, "customer_ref": session["customer_id"],
        "cosine": round(result["score"], 4), "threshold": result["threshold"],
        "spoof_score": round(spoof["score"], 4), "s_verify": round(s_verify, 4),
        "passed": passed, "enrolment_source": result.get("source"),
        "verification_source": source,
        "simulated": source == "demo_clip",
    }, session_id=session_id)
    return {"passed": passed, "source": source, "simulated": source == "demo_clip",
            "cosine": round(result["score"], 4),
            "threshold": round(result["threshold"], 4),
            "spoof_score": round(spoof["score"], 4),
            "s_verify": round(s_verify, 4),
            "enrolment_source": result.get("source"),
            "valid_for_s": VERIFICATION_TTL_SECONDS,
            "valid_for_turns": VERIFICATION_MAX_TURNS,
            "reason": result.get("reason")}


def _fresh_verification(session: sqlite3.Row) -> dict | None:
    """The stored voice check, if it is still good for this turn."""
    if not session["verified_at"]:
        return None
    try:
        when = datetime.fromisoformat(session["verified_at"])
    except (TypeError, ValueError):
        return None
    age = (utcnow() - when).total_seconds()
    turns = session["verified_turns"]
    if age > VERIFICATION_TTL_SECONDS or turns >= VERIFICATION_MAX_TURNS:
        return {"expired": True, "age_s": round(age, 1), "turns_used": turns}
    return {"expired": False, "age_s": round(age, 1), "turns_used": turns,
            "cosine": session["verified_score"], "spoof": session["verified_spoof"]}


def _authenticate(conn: sqlite3.Connection, session: sqlite3.Row, trace: ComplianceTrace,
                  tier: int, audio: bytes | None, st: dict) -> AuthOutcome | None:
    """Decide whether we know who is speaking.

    Three ways a turn can be authenticated, in order of strength:

      passive   the caller spoke this turn, so the query audio itself is the
                sample. This is what the paper describes.
      recent    a live voice check happened in the last few minutes and has
                turns left on it. Real evidence, just not from this second.
      none      no sample. The turn does not proceed to account data.

    What is NOT here any more: scoring a seeded WAV from disk and reporting it
    as the caller's verification. That is what let a tester reach account data
    without ever speaking, and it is why a demo can look like it verified when
    it did not.
    """
    if tier < TIER_REQUIRING_VERIFICATION:
        trace.auth = AuthOutcome(method="none", passed=True,
                                 reason="tier 0 is public information, no authentication")
        return trace.auth

    from .security import antispoof, speaker

    if audio is not None:
        with trace.stage("speaker_verify", audio, component="speaker_verify") as rec:
            result = speaker.verify(conn, session["customer_id"], audio)
            spoof = antispoof.score(audio)
            s_verify = result["score"] * spoof["score"]
            passed = bool(result["score"] >= result["threshold"] and spoof["bona_fide"])
            trace.auth = AuthOutcome(
                method="speaker", speaker_score=round(result["score"], 4),
                spoof_score=round(spoof["score"], 4), s_verify=round(s_verify, 4),
                threshold=result["threshold"], passed=passed,
                reason=("verified on this turn's audio" if passed
                        else "cosine below threshold on this turn's audio"))
            rec.outputs = {"mode": "passive", "cosine": round(result["score"], 4),
                           "threshold": result["threshold"],
                           "spoof_score": round(spoof["score"], 4),
                           "bona_fide": spoof["bona_fide"],
                           "s_verify": round(s_verify, 4),
                           "enrolment_source": result.get("source")}
            rec.confidence = round(s_verify, 4)
            rec.model_id = f"{result['model_id']} x {spoof['model_id']}"
            rec.notes = "passive verification on the audio of this turn"
        with trace.stage("antispoof", audio, component="antispoof") as rec:
            rec.outputs = spoof
            rec.confidence = spoof["score"]
            rec.model_id = spoof["model_id"]
            rec.notes = "classical LFCC and GMM baseline, not a trained AASIST countermeasure"
        st["auth"] = trace.auth.model_dump()
        return trace.auth

    fresh = _fresh_verification(session)
    with trace.stage("speaker_verify", session["session_id"], component="speaker_verify") as rec:
        if fresh and not fresh["expired"]:
            s_verify = (fresh["cosine"] or 0.0) * (fresh["spoof"] or 0.0)
            trace.auth = AuthOutcome(
                method="speaker", speaker_score=round(fresh["cosine"] or 0.0, 4),
                spoof_score=round(fresh["spoof"] or 0.0, 4),
                s_verify=round(s_verify, 4), threshold=None, passed=True,
                reason=f"live voice check {fresh['age_s']:.0f}s ago, "
                       f"{fresh['turns_used']} of {VERIFICATION_MAX_TURNS} turns used")
            rec.outputs = {"mode": "recent", **fresh, "s_verify": round(s_verify, 4),
                           "verification_source": session["verified_source"]}
            rec.capability = ("SIMULATED" if session["verified_source"] == "demo_clip"
                              else rec.capability)
            rec.confidence = round(s_verify, 4)
            rec.notes = (
                "typed turn, carried by a voice check from earlier in this session; "
                "it expires. " + ("That check ran against a SEEDED CLIP, not a live "
                                  "speaker: a demonstration of the mechanism, not "
                                  "evidence about who is calling."
                                  if session["verified_source"] == "demo_clip"
                                  else "That check was a live recording."))
            conn.execute("UPDATE sessions SET verified_turns=verified_turns+1"
                         " WHERE session_id=?", (session["session_id"],))
            conn.commit()
        else:
            why = ("the earlier voice check has expired" if fresh
                   else "no voice check has been done in this session")
            trace.auth = AuthOutcome(method="speaker", passed=False, s_verify=0.0,
                                     reason=why)
            rec.outputs = {"mode": "none", "expired": bool(fresh), "reason": why}
            rec.notes = ("no live sample, so s_verify is 0, which raises R through the "
                         "(1 - s_verify) term and holds the turn")
        rec.model_id = speaker.model_id()
    st["auth"] = trace.auth.model_dump()
    return trace.auth


def _act(conn, session, trace: ComplianceTrace, verdict: dict, auth, otp_needed: bool,
         lang: str, core: MockCore, st: dict) -> dict:
    intent, slots = trace.intent, trace.slots
    customer_id = session["customer_id"]

    def wrap(out: dict, decision: str, reason: str) -> dict:
        return {"decision": decision, "reason": reason,
                "action_taken": out["action_taken"], "result": out["result"],
                "reply": actions.pick(out["reply"], lang)}

    # Tier 3 always goes to a human, whatever the score said. The customer
    # still hears WHY, so an investment-advice request gets the explanation
    # about registered advisers rather than a generic transfer.
    if trace.risk_tier >= 3:
        packet = build_handover_packet(conn, session, trace,
                                       reason=verdict["reason"])
        out = (actions.investment_advice(trace) if intent == "investment_advice"
               else actions.escalate(trace, verdict["reason"], packet["queue_position"]))
        trace.handover_packet_ref = packet["handover_id"]
        return wrap(out, "escalated", verdict["reason"])

    # Verification is needed and did not pass: ask for it, do not act.
    if trace.risk_tier >= TIER_REQUIRING_VERIFICATION and not (auth and auth.passed):
        out = actions.need_verification(auth.reason if auth else "")
        return wrap(out, "escalated",
                    f"speaker verification did not pass: {auth.reason if auth else 'no auth'}")

    # Tier 2 needs OTP and a spoken read-back before anything commits.
    if otp_needed:
        st["pending"] = {"intent": intent, "slots": slots, "lang": lang,
                         "trace_id": str(trace.trace_id), "stage": "otp"}
        out = actions.request_otp(intent or "")
        trace.auth = trace.auth or AuthOutcome(method="speaker+otp")
        trace.auth.method = "speaker+otp"
        trace.auth.otp_required = True
        return wrap(out, "escalated", "tier 2 requires a one time password and a read-back")

    if not verdict["automate"]:
        out = (actions.refuse(trace, verdict["reason"]) if verdict["outcome"] == "refused"
               else actions.escalate(trace, verdict["reason"]))
        if verdict["outcome"] == "escalated":
            packet = build_handover_packet(conn, session, trace, reason=verdict["reason"])
            trace.handover_packet_ref = packet["handover_id"]
        return wrap(out, verdict["outcome"], verdict["reason"])

    return wrap(_dispatch(core, customer_id, trace, intent, slots), "automated",
                verdict["reason"])


def _dispatch(core: MockCore, customer_id: str | None, trace: ComplianceTrace,
              intent: str | None, slots: dict) -> dict:
    """Route an approved turn to exactly one action. No decisions happen here;
    the gate already made them."""
    if intent in GROUNDED_INTENTS:
        return actions.answer_from_policy(trace)
    if intent == "get_balance":
        return actions.get_balance(core, customer_id, trace)
    if intent == "mini_statement":
        n = (slots.get("date_range") or {}).get("count", 3)
        return actions.mini_statement(core, customer_id, trace, limit=max(1, min(int(n), 10)))
    if intent == "cheque_status":
        return actions.cheque_status(core, customer_id, trace, slots.get("cheque_number"))
    if intent == "branch_ifsc":
        return actions.branch_ifsc(core, trace, trace.transcript or "")
    if intent == "block_card":
        return actions.block_card(core, customer_id, trace, slots.get("card_last4"))
    if intent == "limit_change":
        return actions.limit_change(core, customer_id, trace, slots.get("card_last4"),
                                    slots.get("amount"))
    if intent == "add_payee":
        return actions.add_payee(core, customer_id, trace, slots.get("payee"),
                                 slots.get("account_last4"))
    if intent == "fund_transfer":
        return actions.fund_transfer(core, customer_id, trace, slots.get("payee"),
                                     slots.get("amount"))
    if intent == "investment_info":
        return actions.investment_info(core, customer_id, trace, slots,
                                       trace.transcript or "")
    if intent == "investment_advice":
        return actions.investment_advice(trace)
    return actions.out_of_scope(trace)


def _resume_pending(conn, session, trace: ComplianceTrace, pending: dict,
                    otp: str | None, confirm: bool | None, lang: str,
                    core: MockCore) -> ComplianceTrace:
    """Second and third legs of a tier 2 transaction: OTP, then read-back."""
    st = state(session["session_id"])
    trace.intent = pending["intent"]
    trace.slots = pending["slots"]
    trace.risk_tier = max(2, session["tier_floor"])
    trace.risk_score = None
    trace.risk_components = {"note": "carried over from the originating turn",
                             "origin_trace_id": pending["trace_id"]}
    trace.auth = AuthOutcome(method="speaker+otp", otp_required=True)

    if pending["stage"] == "otp":
        with trace.stage("otp", {"submitted": bool(otp)}, component="otp") as rec:
            ok = (otp or "").strip() == OTP_DEMO_CODE
            rec.outputs = {"passed": ok, "channel": "SIMULATED"}
            rec.notes = "fixed demo code, no SMS gateway"
        trace.auth.otp_passed = ok
        if not ok:
            trace.decision, trace.decision_reason = "escalated", "incorrect one time password"
            trace.action_taken = "otp_failed"
            trace.reply_text = {
                "en": "That code did not match. Let me put you through to a colleague.",
                "hi": "यह कोड मेल नहीं खाया। मैं आपको एक सहकर्मी से जोड़ देता हूँ।",
                "mr": "हा कोड जुळला नाही. मी तुम्हाला एका सहकाऱ्याकडे जोडतो.",
            }[lang if lang in ("en", "hi", "mr") else "en"]
            st["pending"] = None
        else:
            en, hi, mr = actions.readback_summary(pending["intent"], pending["slots"])
            out = actions.readback(en, hi, mr)
            trace.auth.readback_text = en
            st["pending"] = pending | {"stage": "readback"}
            trace.decision, trace.decision_reason = "escalated", "awaiting spoken read-back confirmation"
            trace.action_taken, trace.action_result = out["action_taken"], out["result"]
            trace.reply_text = actions.pick(out["reply"], lang)
    else:
        with trace.stage("readback", {"confirmed": confirm}, component="nlu") as rec:
            rec.outputs = {"confirmed": bool(confirm)}
        trace.auth.otp_passed = True
        trace.auth.readback_confirmed = bool(confirm)
        st["pending"] = None
        if not confirm:
            trace.decision, trace.decision_reason = "refused", "customer did not confirm the read-back"
            trace.action_taken = "readback_declined"
            trace.reply_text = {
                "en": "Understood, I have not changed anything. Your account is exactly as it was.",
                "hi": "ठीक है, मैंने कुछ भी नहीं बदला। आपका खाता जैसा था वैसा ही है।",
                "mr": "ठीक आहे, मी काहीही बदललेले नाही. तुमचे खाते जसे होते तसेच आहे.",
            }[lang if lang in ("en", "hi", "mr") else "en"]
        else:
            out = _dispatch(core, session["customer_id"], trace, pending["intent"],
                            pending["slots"])
            trace.decision = "automated"
            trace.decision_reason = "tier 2 completed: verification, one time password and read-back all passed"
            trace.action_taken, trace.action_result = out["action_taken"], out["result"]
            trace.reply_text = actions.pick(out["reply"], lang)

    trace.reply_language = lang
    finalise(conn, session, trace)
    conn.execute("UPDATE sessions SET turn_count=turn_count+1 WHERE session_id=?",
                 (session["session_id"],))
    conn.commit()
    return trace


# ---------------------------------------------------------------- persistence

# Keys whose values are hashes or model identifiers. Running the redactor over
# a SHA-256 digest would be pointless and could tokenise a run of digits inside
# it, so they are left alone.
_SCRUB_SKIP = {"inputs_digest", "hash", "prev_hash", "sig", "trace_digest",
               "model_id", "record_id", "trace_id", "session_id", "consent_ref"}


def _scrub_tree(node, scrub, numbers: dict[str, str] | None = None):
    """Apply the redactor to every string in a nested structure.

    Numbers are checked too. A parser that reads a phone number as an amount
    puts the identifier into the trace as a float, where a string-only
    redactor walks straight past it. That happened once; this is the guard.
    """
    numbers = numbers or {}
    if isinstance(node, str):
        return scrub(node)
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        digits = str(int(node)) if float(node).is_integer() else None
        return numbers.get(digits, node) if digits else node
    if isinstance(node, dict):
        return {k: (v if k in _SCRUB_SKIP else _scrub_tree(v, scrub, numbers))
                for k, v in node.items()}
    if isinstance(node, list):
        return [_scrub_tree(v, scrub, numbers) for v in node]
    if isinstance(node, tuple):
        return tuple(_scrub_tree(v, scrub, numbers) for v in node)
    return node


def finalise(conn: sqlite3.Connection, session: sqlite3.Row, trace: ComplianceTrace) -> dict:
    """Redact, store, and append to the ledger. Nothing reaches disk before this."""
    st = state(session["session_id"])
    with trace.stage("pii_redaction", trace.transcript or "", component="pii") as rec:
        counters, seen = st["pii_counters"], st["pii_seen"]

        def scrub(text: str) -> str:
            """Redact and vault in one step, using the session's token map so a
            value keeps the same token across every turn of the call."""
            red = pii.redact(text, counters, seen)
            for token, raw in red.tokens.items():
                crypto.vault_put(conn, session["session_id"], token,
                                 red.token_types[token], raw)
            trace.pii_tokens.update(red.token_types)
            return red.text

        trace.transcript = scrub(trace.transcript or "")
        # The reply can carry identifiers too, for instance an account last four
        # read back to the customer, so it goes through the same scrub.
        if trace.reply_text:
            trace.reply_text = scrub(trace.reply_text)
        # Redacting only the transcript is not enough. Stage outputs quote the
        # text they worked on: the language spans hold the words verbatim, the
        # NLU record echoes the slots, an action result can carry an account
        # number. Every one of those is about to be written to disk, so the
        # whole tree is scrubbed, not just the headline field.
        for span in trace.language_spans:
            span.text = scrub(span.text)
        # Digits-only form of every vaulted value, so an identifier that
        # reached the trace as a number is caught as well as one that reached
        # it as text.
        numeric = {__import__("re").sub(r"\D", "", raw): token
                   for raw, token in seen.items() if __import__("re").sub(r"\D", "", raw)}
        for record in trace.stages:
            record.outputs = _scrub_tree(record.outputs, scrub, numeric)
            if record.notes:
                record.notes = scrub(record.notes)
        trace.slots = _scrub_tree(trace.slots, scrub, numeric)
        trace.action_result = _scrub_tree(trace.action_result, scrub, numeric)
        if trace.auth and trace.auth.readback_text:
            trace.auth.readback_text = scrub(trace.auth.readback_text)
        trace.redacted = True
        rec.outputs = {"tokens": sorted(trace.pii_tokens.items()),
                       "n_tokens": len(trace.pii_tokens)}
        rec.model_id = "regex+luhn+verhoeff"

    body = trace.model_dump(mode="json")
    conn.execute(
        "INSERT OR REPLACE INTO traces (trace_id, session_id, turn_index, created_at, body)"
        " VALUES (?,?,?,?,?)",
        (str(trace.trace_id), str(trace.session_id), trace.turn_index,
         trace.created_at.isoformat(), __import__("json").dumps(body, ensure_ascii=False)))
    conn.commit()

    record = ledger.append(conn, "turn", {
        "trace_id": str(trace.trace_id), "session_id": str(trace.session_id),
        "turn_index": trace.turn_index, "consent_ref": str(trace.consent_ref),
        "intent": trace.intent, "intent_confidence": trace.intent_confidence,
        "c_final": trace.fused_confidence,
        "risk_score": trace.risk_score, "risk_tier": trace.risk_tier,
        "decision": trace.decision, "decision_reason": trace.decision_reason,
        "action_taken": trace.action_taken,
        "citations": [{"doc_id": p.doc_id, "version": p.version} for p in trace.retrieved],
        "auth": trace.auth.model_dump(mode="json") if trace.auth else None,
        "pii_tokens": trace.pii_tokens,
        "trace_digest": __import__("hashlib").sha256(
            __import__("json").dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest(),
    }, session_id=str(trace.session_id))
    return record


def build_handover_packet(conn: sqlite3.Connection, session: sqlite3.Row,
                          trace: ComplianceTrace, reason: str) -> dict:
    """The context packet an agent receives, so the customer never repeats
    themselves. Redacted: the agent sees tokens, not identifiers."""
    import json
    prior = [json.loads(r["body"]) for r in conn.execute(
        "SELECT body FROM traces WHERE session_id=? ORDER BY turn_index",
        (str(trace.session_id),))]
    packet = {
        "session_id": str(trace.session_id),
        "trace_id": str(trace.trace_id),
        "customer_ref": session["customer_id"],
        "reason": reason,
        "intent": trace.intent,
        "risk_score": trace.risk_score,
        "risk_tier": trace.risk_tier,
        "languages": sorted({s.lang for s in trace.language_spans}),
        "code_mix_index": trace.code_mix_index,
        "auth": trace.auth.model_dump(mode="json") if trace.auth else None,
        "conversation": [{"turn": p["turn_index"], "transcript": p.get("transcript"),
                          "intent": p.get("intent"), "decision": p.get("decision"),
                          "reply": p.get("reply_text")} for p in prior],
        "current_turn": {"transcript": trace.transcript, "reply": trace.reply_text},
        "no_automated_action_taken": True,
    }
    hid = f"HND{uuid.uuid4().hex[:8].upper()}"
    queue_position = conn.execute(
        "SELECT COUNT(*) c FROM handovers WHERE status='queued'").fetchone()["c"] + 1
    conn.execute(
        "INSERT INTO handovers (handover_id, trace_id, session_id, created_at, reason, packet)"
        " VALUES (?,?,?,?,?,?)",
        (hid, str(trace.trace_id), str(trace.session_id), utcnow().isoformat(), reason,
         __import__("json").dumps(packet, ensure_ascii=False)))
    conn.commit()
    ledger.append(conn, "handover", {"handover_id": hid, "trace_id": str(trace.trace_id),
                                     "reason": reason, "queue_position": queue_position},
                  session_id=str(trace.session_id))
    return {"handover_id": hid, "queue_position": queue_position, "packet": packet}


def withdraw_consent(conn: sqlite3.Connection, session_id: str) -> dict:
    """DPDP erasure. Purge the vault and transcripts, append a purge record.

    The ledger keeps hashes and tokens only, never identifiers, so it survives
    the purge. Deleting it would destroy the evidence that the purge happened.
    """
    now = utcnow().isoformat()
    conn.execute("UPDATE sessions SET withdrawn_at=? WHERE session_id=?", (now, session_id))
    conn.execute("UPDATE consents SET withdrawn_at=? WHERE session_id=?", (now, session_id))
    purged = crypto.purge_session(conn, session_id)
    conn.commit()
    SESSION_STATE.pop(session_id, None)
    record = ledger.append(conn, "purge", {
        "session_id": session_id, "withdrawn_at": now,
        "vault_rows_deleted": purged["vault_rows_deleted"],
        "traces_deleted": purged["traces_deleted"],
        "basis": "consent withdrawn by data principal",
    }, session_id=session_id)
    return purged | {"session_id": session_id, "withdrawn_at": now,
                     "ledger_index": record["idx"], "ledger_hash": record["hash"]}
