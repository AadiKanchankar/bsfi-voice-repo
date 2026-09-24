"""FastAPI entrypoint and WebSocket session handler.

Every endpoint except /capabilities and /health requires a JWT. The role
matrix lives in security/rbac.py and tests/test_rbac.py walks every cell of it,
including the one that matters most: a customer token must not be able to read
the compliance export.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Any

from fastapi import (Depends, FastAPI, File, Form, HTTPException, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import db, turn
from .capabilities import registry_dict
from .call import CallEnded, TurnInFlight
from .config import DB_PATH, LANGUAGES, ROLES
from .security import ledger, rbac
from .trace import utcnow

STARTED_AT = time.time()
CONN = None
METRICS: dict[str, Any] = {"turns": 0, "decisions": {}, "stage_ms": {}, "errors": 0}

# Warming runs in the background now, so its state is worth reporting: the
# first greeting is slower until it finishes, and a blank screen with no
# explanation is what this replaces.
WARMED: dict[str, Any] = {"state": "pending", "detail": ""}

# Lines the assistant says verbatim on many calls. Pre-synthesised at startup
# so none of them is ever on a caller's clock. Anything with a balance, a
# payee or a name in it is deliberately absent: that would be caching spoken
# personal data.
FIXED_LINES: dict[str, dict[str, str]] = {
    "otp_prompt": {
        "en": "I have sent a one time password to your registered mobile number. "
              "Please say the six digits.",
        "hi": "मैंने आपके पंजीकृत मोबाइल नंबर पर एक ओटीपी भेजा है। कृपया छह अंक बोलिए।",
        "mr": "मी तुमच्या नोंदणीकृत मोबाइल नंबरवर ओटीपी पाठवला आहे. कृपया सहा अंक सांगा.",
    },
    "hold": {
        "en": "Thank you for holding. I am still finding someone for you.",
        "hi": "प्रतीक्षा के लिए धन्यवाद। मैं अब भी आपके लिए किसी को खोज रहा हूँ।",
        "mr": "प्रतीक्षा केल्याबद्दल धन्यवाद. मी अजूनही तुमच्यासाठी कोणीतरी शोधत आहे.",
    },
    "checking": {
        "en": "Let me check that for you.",
        "hi": "मैं आपके लिए यह देखता हूँ।",
        "mr": "मी तुमच्यासाठी ते तपासतो.",
    },
}


def _warm_models() -> None:
    """Load the lazy models at startup rather than inside the first turn.

    Without this the first live turn pays about 3.5 seconds to load the
    embedding model, which on stage looks like the system hanging. Failures
    here are logged and ignored: a missing model must not stop the server from
    booting, because the text path and the ledger still work without it.
    """
    for name, load in (("embeddings", lambda: __import__(
            "app.pipeline.embed", fromlist=["embed"]).get_model()),):
        try:
            t0 = time.perf_counter()
            load()
            print(f"warmed {name} in {time.perf_counter() - t0:.1f}s", flush=True)
        except Exception as exc:                          # noqa: BLE001
            print(f"could not warm {name}: {exc}", flush=True)

    # Pre-synthesise the lines that never vary. Speaking the greeting costs
    # about 2.8 seconds the first time and nothing thereafter, and the
    # greeting is the one line every single call starts with.
    try:
        from .pipeline import tts
        from .turn import consent_notice
        prompts = []
        for lang in LANGUAGES:
            notice = consent_notice(lang).get(lang)
            if notice:
                prompts.append((notice, lang))
        prompts += [(FIXED_LINES[key][lang], lang)
                    for key in FIXED_LINES for lang in FIXED_LINES[key]]
        t0 = time.perf_counter()
        n = tts.prewarm(prompts)
        print(f"pre-synthesised {n} fixed prompts in "
              f"{time.perf_counter() - t0:.1f}s", flush=True)
        WARMED.update(state="ready", detail=f"{n} prompts pre-synthesised")
    except Exception as exc:                              # noqa: BLE001
        print(f"could not pre-synthesise prompts: {exc}", flush=True)
        WARMED.update(state="partial", detail=str(exc)[:120])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the database, then start serving. Warm up behind that.

    Warming used to be awaited here, which meant the server accepted no
    connections until it finished. Pre-synthesising twelve fixed prompts
    takes about 38 seconds, so `make demo` looked dead for the best part of
    a minute and every reload cost the same again. The browser's own error
    said "the backend is not responding", which was true and unhelpful.

    Warming is an optimisation: the greeting is faster once it has run, and
    correct before it has. So it belongs off the startup path, in a thread
    that fills the caches while the server is already answering.
    """
    global CONN, WARMED
    CONN = db.init_db(DB_PATH)
    if os.environ.get("BFSI_SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_models, name="warmup", daemon=True).start()
    else:
        WARMED = {"state": "skipped", "detail": "BFSI_SKIP_WARMUP=1"}
    yield
    if CONN:
        CONN.close()


app = FastAPI(title="Compliance-Aware Multilingual Voice Assistant for BFSI",
              version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def conn():
    if CONN is None:
        raise HTTPException(503, "database not ready")
    return CONN


# ---------------------------------------------------------------- models

class ConsentRequest(BaseModel):
    customer_id: str | None = None
    device_id: str | None = None
    voice_clip: str | None = None
    languages: str = ",".join(LANGUAGES)
    accepted: bool = True


class TextTurnRequest(BaseModel):
    session_id: str
    text: str | None = None
    otp: str | None = None
    confirm: bool | None = None
    asr_confidence: float | None = None


class TokenRequest(BaseModel):
    subject: str
    role: str


class RegisterRequest(BaseModel):
    name: str
    mobile: str | None = None
    language: str = "en"


class IdentifyRequest(BaseModel):
    identifier: str


# ---------------------------------------------------------------- open endpoints

# Bumped whenever an endpoint the browser depends on is added. The frontend
# refuses to pretend everything is fine when it is talking to an older
# backend: two screenshots of "405 Method Not Allowed" and "404 Not Found"
# were both a new page against a stale API, with nothing on screen saying so.
API_FEATURES = [
    "customers.register", "session.identify", "recordings", "compliance.search",
    "call.state", "tts.plan", "providers", "escalation.cases", "agent.console",
]


@app.get("/health")
def health():
    """Liveness, plus what this build can actually do.

    The feature list is not decoration. `make demo` used to run uvicorn
    without reload, so a backend started before a code change kept serving
    the old API while the browser hot-reloaded to the new frontend. The
    symptom was a 405 on a button that obviously exists. Now the page can
    see the mismatch and say so.
    """
    return {"ok": True, "uptime_s": round(time.time() - STARTED_AT, 1),
            "features": API_FEATURES, "warmup": WARMED}


@app.get("/capabilities")
def capabilities():
    """The honesty registry. Deliberately unauthenticated: anybody looking at
    this system should be able to see what is real in it without a token."""
    return {"capabilities": registry_dict(),
            "legend": {
                "REAL": "a genuine implementation of the component named",
                "BASELINE": "real but deliberately simpler than the paper's target",
                "SIMULATED": "not implemented, stands in for an external system"},
            "synthetic_data_notice": (
                "All customers, accounts, cards, transactions and enrolled voices in "
                "this system are synthetic and generated by a seed script. No real "
                "personal data is present.")}


@app.post("/auth/demo-token")
def demo_token(req: TokenRequest):
    """Demo-only token issuer. There is no identity provider in this build, and
    the capability registry records that RBAC is demo-scale."""
    if req.role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    return {"token": rbac.issue_token(req.subject, req.role), "role": req.role,
            "note": "demo issuer, no identity provider; production design names Keycloak"}


@app.get("/customers")
def customers(principal: Annotated[dict, Depends(rbac.require("session:create"))]):
    """The synthetic customers a demo can open a session against.

    The console builds its picker from this rather than a hardcoded list,
    which is how CUST9001 came to exist in the seed data and not in the UI.
    """
    from .config import PRESENTER_ID
    rows = conn().execute(
        "SELECT c.customer_id, c.name, c.language,"
        "       (SELECT COUNT(*) FROM speakers s WHERE s.customer_id=c.customer_id) AS enrolled,"
        "       (SELECT source FROM speakers s WHERE s.customer_id=c.customer_id) AS source,"
        "       (SELECT COUNT(*) FROM accounts a WHERE a.customer_id=c.customer_id) AS accounts,"
        "       (SELECT COUNT(*) FROM holdings h WHERE h.customer_id=c.customer_id) AS holdings"
        " FROM customers c ORDER BY c.customer_id")
    out = []
    for r in rows:
        d = dict(r)
        d["is_presenter"] = d["customer_id"] == PRESENTER_ID
        d["enrolled"] = bool(d["enrolled"])
        out.append(d)
    # Presenter first: it is the one with a full history behind it.
    out.sort(key=lambda d: (not d["is_presenter"], d["customer_id"]))
    return {"customers": out, "presenter_id": PRESENTER_ID}


@app.post("/customers")
def register_customer(req: RegisterRequest,
                      principal: Annotated[dict, Depends(rbac.require("enroll"))]):
    """Register a customer so a voice can be enrolled against them.

    Only the last four digits of the mobile number are stored. That is enough
    to identify a caller who states it, and it is the least we can keep.
    """
    from .banking import registry
    if not req.name.strip():
        raise HTTPException(400, "a name is required")
    if req.language not in LANGUAGES:
        raise HTTPException(400, f"language must be one of {LANGUAGES}")
    return registry.create_customer(conn(), name=req.name.strip(),
                                    mobile=req.mobile, language=req.language)


# ---------------------------------------------------------------- session

@app.post("/session/consent")
def create_consent(req: ConsentRequest,
                   principal: Annotated[dict, Depends(rbac.require("session:create"))]):
    if not req.accepted:
        raise HTTPException(400, "consent is required before a session can open")
    out = turn.create_session(conn(), req.customer_id, req.device_id,
                              req.voice_clip, req.languages)
    return out


@app.post("/session/{session_id}/withdraw")
def withdraw(session_id: str,
             principal: Annotated[dict, Depends(rbac.require("consent:withdraw"))]):
    try:
        return turn.withdraw_consent(conn(), session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/session/{session_id}/identify")
def identify(session_id: str, req: IdentifyRequest,
             principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Bind an anonymous call to a customer by stated mobile or customer id."""
    try:
        return turn.identify_caller(conn(), session_id, req.identifier)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:          # consent withdrawn on this session
        raise HTTPException(403, str(exc))
    except ValueError as exc:               # already identified
        raise HTTPException(409, str(exc))


@app.get("/session/{session_id}/traces")
def session_traces(session_id: str,
                   principal: Annotated[dict, Depends(rbac.require("trace:read_own"))]):
    rows = conn().execute(
        "SELECT body FROM traces WHERE session_id=? ORDER BY turn_index", (session_id,))
    return {"session_id": session_id, "traces": [json.loads(r["body"]) for r in rows]}


# ---------------------------------------------------------------- call control

class InterruptRequest(BaseModel):
    played_ms: float | None = None
    played_chars: int | None = None
    reply_chars: int | None = None
    source: str = "barge_in"


def _call_error(exc: Exception) -> HTTPException:
    from .call import BadTransition, CallEnded, TurnInFlight
    if isinstance(exc, CallEnded):
        return HTTPException(409, str(exc))
    if isinstance(exc, TurnInFlight):
        return HTTPException(409, str(exc))
    if isinstance(exc, BadTransition):
        return HTTPException(409, str(exc))
    raise exc


@app.get("/call/{call_id}/state")
def call_state(call_id: str,
               principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """The server owns the call state. The client reads it, it does not set it."""
    from . import call as callsm
    return callsm.state(call_id)


@app.post("/call/{call_id}/interrupt")
def call_interrupt(call_id: str, req: InterruptRequest,
                   principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Stop speaking. Works in every state.

    `played_ms` and `played_chars` are how much of the reply the caller
    actually heard. They are recorded rather than assumed, because a reply cut
    off after four words was not delivered and an audit that says it was is
    wrong about what the caller was told.
    """
    from . import call as callsm
    try:
        return callsm.interrupt(conn(), call_id, played_ms=req.played_ms,
                                played_chars=req.played_chars,
                                reply_chars=req.reply_chars, source=req.source)
    except Exception as exc:                        # noqa: BLE001
        raise _call_error(exc)


@app.post("/call/{call_id}/end")
def call_end(call_id: str,
             principal: Annotated[dict, Depends(rbac.require("turn:submit"))],
             reason: str = "caller hung up"):
    """Hang up. Works in every state, including with a turn in flight."""
    from . import call as callsm
    return callsm.end_call(conn(), call_id, reason=reason)


# ---------------------------------------------------------------- turns

def _record_metrics(t) -> None:
    METRICS["turns"] += 1
    key = t.decision or "unknown"
    METRICS["decisions"][key] = METRICS["decisions"].get(key, 0) + 1
    for stage in t.stages:
        METRICS["stage_ms"].setdefault(stage.stage, []).append(stage.duration_ms)


@contextmanager
def _one_turn(session_id: str):
    """Run the body as the call's single active turn.

    Yields the cancel token and the turn id. Entering supersedes any turn
    already in flight, which is what a caller speaking again means, and
    leaving moves the call to SPEAKING. A turn that gets superseded while it
    runs raises Cancelled here and is reported as such rather than returning
    a second answer.
    """
    from . import call as callsm
    row = conn().execute("SELECT call_id FROM sessions WHERE session_id=?",
                         (session_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown session {session_id}")
    call_id = row["call_id"]
    if not call_id:
        yield None, None           # a session with no call predates R1
        return
    turn_id, token = callsm.begin_turn(conn(), call_id)
    try:
        yield token, turn_id
    except callsm.Cancelled as exc:
        raise HTTPException(409, f"turn {turn_id} was superseded: {exc}")
    finally:
        callsm.finish_turn(conn(), call_id, turn_id)


@app.post("/turn/text")
def text_turn(req: TextTurnRequest,
              principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """The text fallback. Everything after the transcript is identical to the
    voice path, which is what makes the demo survive a dead microphone."""
    try:
        with _one_turn(req.session_id) as (token, turn_id):
            t = turn.run_turn(conn(), req.session_id, text=req.text, otp=req.otp,
                              confirm=req.confirm, asr_confidence=req.asr_confidence,
                              cancel=token)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except (CallEnded, TurnInFlight) as exc:
        raise HTTPException(409, str(exc))
    _record_metrics(t)
    return {**t.model_dump(mode="json"), "turn_id": turn_id}


@app.post("/turn/audio")
async def audio_turn(session_id: Annotated[str, Form()],
                     audio: Annotated[UploadFile, File()],
                     principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    data = await audio.read()
    try:
        with _one_turn(session_id) as (token, turn_id):
            t = await asyncio.to_thread(turn.run_turn, conn(), session_id,
                                        audio=data, cancel=token)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except (CallEnded, TurnInFlight) as exc:
        raise HTTPException(409, str(exc))
    del data                       # the buffer is dropped as soon as the turn is done
    _record_metrics(t)
    return {**t.model_dump(mode="json"), "turn_id": turn_id}


@app.get("/trace/{trace_id}")
def get_trace(trace_id: str,
              principal: Annotated[dict, Depends(rbac.require("trace:read_own"))]):
    row = conn().execute("SELECT body FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"no trace {trace_id}")
    return json.loads(row["body"])


# ---------------------------------------------------------------- speech out

@app.get("/tts/plan")
def speak_plan(text: str, language: str = "en",
               principal: Annotated[dict, Depends(rbac.require("turn:submit"))] = None):
    """Split a reply into the phrases it will be spoken in.

    Synthesis is 71% of the wait between a caller finishing and hearing an
    answer, and a reply is about four phrases long. Speaking the first one as
    soon as it exists, while the rest is still being made, is the single
    largest latency win available and it needs no streaming protocol: the
    client asks for the phrases, then fetches and plays them in order.
    """
    from .pipeline.prosody import split_phrases
    phrases = [p for p, _ in split_phrases(text) if p.strip()]
    return {"phrases": phrases or [text], "language": language}


@app.get("/tts")
def speak(text: str, language: str = "en", fixed: bool = False,
          principal: Annotated[dict, Depends(rbac.require("turn:submit"))] = None):
    """`fixed=true` marks a line that never varies (greeting, notice, OTP
    prompt) as cacheable. It is opt in because most replies carry a balance
    or a payee, and caching those would leave spoken personal data in
    memory after the call."""
    from .pipeline import tts
    out = tts.synthesize(text, language, cacheable=fixed)
    if not out["available"]:
        raise HTTPException(503, out["error"])
    return Response(content=out["audio"], media_type="audio/wav",
                    headers={"X-Piper-Voice": out["voice"],
                             "X-Cached": str(bool(out.get("cached"))).lower()})


# ---------------------------------------------------------------- enrolment

@app.post("/enroll")
async def enroll(customer_id: Annotated[str, Form()],
                 clips: Annotated[list[UploadFile], File()],
                 principal: Annotated[dict, Depends(rbac.require("enroll"))]):
    from .security import speaker
    if len(clips) < 3:
        raise HTTPException(400, "three enrolment clips are required")
    data = [await c.read() for c in clips]
    out = await asyncio.to_thread(speaker.enrol, conn(), customer_id, data, "live")
    ledger.append(conn(), "enrolment",
                  {"customer_ref": customer_id, "n_clips": len(data), "source": "live",
                   "mean_pairwise_cosine": out["mean_pairwise_cosine"]})
    return out


@app.post("/verify")
async def verify_voice(session_id: Annotated[str, Form()],
                       audio: Annotated[UploadFile, File()],
                       principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Run a live voice check for this session.

    This is the only thing that authenticates a caller. A turn carries the
    result for a few minutes and a few turns, then it expires and the caller
    is asked again.
    """
    data = await audio.read()
    try:
        out = await asyncio.to_thread(turn.record_verification, conn(), session_id, data)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    del data
    return out


@app.post("/verify/demo")
def verify_demo(session_id: Annotated[str, Form()],
                principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Dead-microphone fallback: run the check against the seeded clip attached
    to the session. Recorded as SIMULATED in the trace and in the ledger,
    because it demonstrates the mechanism rather than checking a speaker."""
    try:
        return turn.record_verification(conn(), session_id, None, source="demo_clip")
    except KeyError as exc:
        raise HTTPException(404, str(exc))


# ---------------------------------------------------------------- escalation

class IntakeRequest(BaseModel):
    answers: dict


class ProtectiveRequest(BaseModel):
    action: str
    customer_id: str
    confirmed: bool = False
    case_id: str | None = None
    call_id: str | None = None


class AgentReplyRequest(BaseModel):
    agent_id: str
    text: str
    language: str = "en"


class CloseRequest(BaseModel):
    agent_id: str
    outcome: str


@app.get("/cases/{case_id}/intake")
def case_intake_questions(case_id: str,
                          principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """What to ask while the caller waits, chosen by why they are waiting."""
    from . import escalation
    row = conn().execute("SELECT reason FROM cases WHERE case_id=?",
                         (case_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"no case {case_id}")
    return {"case_id": case_id, "reason": row["reason"],
            "questions": escalation.intake_questions(row["reason"])}


@app.post("/cases/{case_id}/intake")
def case_intake(case_id: str, req: IntakeRequest,
                principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    from . import escalation
    try:
        return escalation.record_intake(conn(), case_id, req.answers)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.get("/protective-actions")
def protective_actions(reason: str,
                       principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """What may be offered for this escalation. Reads the whitelist."""
    from . import escalation
    return {"reason": reason, "actions": escalation.available_actions(reason)}


@app.post("/protective-action")
def do_protective_action(req: ProtectiveRequest,
                         principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Reduce harm while the caller waits. Never resolve anything.

    Refuses anything not on the enabled whitelist, and refuses without an
    explicit yes. Both refusals are the point.
    """
    from . import escalation
    try:
        return escalation.perform_protective_action(
            conn(), name=req.action, customer_id=req.customer_id,
            case_id=req.case_id, confirmed=req.confirmed, call_id=req.call_id)
    except escalation.NotWhitelisted as exc:
        raise HTTPException(403, str(exc))


@app.get("/agent/queue")
def agent_queue(principal: Annotated[dict, Depends(rbac.require("handover:read"))],
                status: str = "open"):
    from . import escalation
    return {"status": status, "cases": escalation.queue(conn(), status)}


@app.post("/agent/cases/{case_id}/accept")
def agent_accept(case_id: str, agent_id: str,
                 principal: Annotated[dict, Depends(rbac.require("handover:claim"))]):
    """Take the case and receive everything already known about it, so the
    caller does not repeat themselves."""
    from . import escalation
    try:
        return escalation.accept_case(conn(), case_id, agent_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/agent/cases/{case_id}/reply")
def agent_say(case_id: str, req: AgentReplyRequest,
              principal: Annotated[dict, Depends(rbac.require("handover:claim"))]):
    """The agent types; the caller hears it in their own language, through
    the same normaliser and voice as everything else."""
    from . import escalation
    try:
        return escalation.agent_reply(conn(), case_id, req.agent_id, req.text,
                                      req.language)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/agent/cases/{case_id}/close")
def agent_close(case_id: str, req: CloseRequest,
                principal: Annotated[dict, Depends(rbac.require("handover:claim"))]):
    from . import escalation
    try:
        return escalation.close_case(conn(), case_id, req.agent_id, req.outcome)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/cases/{case_id}/callback")
def case_callback(case_id: str, language: str = "en",
                  principal: Annotated[dict, Depends(rbac.require("turn:submit"))] = None):
    """Nobody free. Log it, give the reference, let them go."""
    from . import escalation
    return escalation.offer_callback(conn(), case_id, language=language)


# ---------------------------------------------------------------- lookup

def _who(principal: dict) -> tuple[str, str]:
    return principal.get("sub", "unknown"), principal.get("role", "unknown")


@app.get("/search")
def search(q: str,
           principal: Annotated[dict, Depends(rbac.require("compliance:search"))]):
    """One box, four kinds of identifier, prefix matching on all of them.

    A miss is a 404 that names what was searched for. The old lookup answered
    200 with an empty list for a typo, a partial id and a customer id alike,
    which is the whole of D22.
    """
    from . import compliance
    actor, role = _who(principal)
    hit = compliance.resolve(conn(), q)
    compliance.record_access(conn(), actor=actor, role=role, action="search",
                             target_type=hit["kind"] if hit else None,
                             target_id=hit["id"] if hit else None,
                             detail=f"q={q!r}", hits=1 if hit else 0)
    if not hit:
        raise HTTPException(404, f"nothing matches {q!r}. Search by call id, session "
                                 f"id, customer id, case id or registered mobile. A "
                                 f"leading part of an id is enough.")
    return hit


@app.get("/calls")
def list_calls(principal: Annotated[dict, Depends(rbac.require("compliance:search"))],
               customer_id: str | None = None, call_id: str | None = None,
               date_from: str | None = None, date_to: str | None = None,
               decision: str | None = None, tier: int | None = None,
               language: str | None = None, limit: int = 50):
    """Filtered call search.

    The change request's sketch names these `from`, `to` and `lang`. `from`
    is a Python keyword, so they are `date_from`, `date_to` and `language`
    here; same fields, spelled so the handler can be written at all.

    `decision` also accepts `interrupted`, which is a property of a turn
    rather than a decision, because an officer asking which calls were
    talked over is asking the same kind of question.
    """
    from . import compliance
    actor, role = _who(principal)
    rows = compliance.search_calls(conn(), customer_id=customer_id, call_id=call_id,
                                   date_from=date_from, date_to=date_to,
                                   decision=decision, tier=tier, language=language,
                                   limit=limit)
    filters = {k: v for k, v in
               {"customer_id": customer_id, "call_id": call_id, "from": date_from,
                "to": date_to, "decision": decision, "tier": tier,
                "language": language}.items() if v is not None}
    compliance.record_access(conn(), actor=actor, role=role, action="search_calls",
                             target_type="calls", detail=json.dumps(filters),
                             hits=len(rows))
    return {"calls": rows, "filters": filters, "count": len(rows)}


@app.get("/calls/{call_id}")
def call_detail(call_id: str,
                principal: Annotated[dict, Depends(rbac.require("compliance:search"))]):
    from . import compliance
    actor, role = _who(principal)
    out = compliance.call_detail(conn(), call_id)
    compliance.record_access(conn(), actor=actor, role=role, action="view_call",
                             target_type="call", target_id=call_id,
                             hits=1 if out else 0)
    if out is None:
        raise HTTPException(404, f"no call {call_id}")
    return out


@app.get("/customers/{customer_id}")
def customer_detail(customer_id: str,
                    principal: Annotated[dict, Depends(rbac.require("compliance:search"))]):
    from . import compliance
    actor, role = _who(principal)
    out = compliance.customer_detail(conn(), customer_id.upper())
    compliance.record_access(conn(), actor=actor, role=role, action="view_customer",
                             target_type="customer", target_id=customer_id,
                             hits=1 if out else 0)
    if out is None:
        raise HTTPException(404, f"no customer {customer_id}")
    return out


@app.get("/customers/{customer_id}/calls")
def customer_calls(customer_id: str,
                   principal: Annotated[dict, Depends(rbac.require("compliance:search"))]):
    from . import compliance
    actor, role = _who(principal)
    rows = compliance.search_calls(conn(), customer_id=customer_id.upper())
    compliance.record_access(conn(), actor=actor, role=role, action="search_calls",
                             target_type="customer", target_id=customer_id,
                             hits=len(rows))
    return {"customer_id": customer_id.upper(), "calls": rows}


@app.get("/cases")
def list_cases(principal: Annotated[dict, Depends(rbac.require("compliance:search"))],
               status: str | None = None, limit: int = 50):
    from . import compliance
    actor, role = _who(principal)
    rows = compliance.list_cases(conn(), status=status, limit=limit)
    compliance.record_access(conn(), actor=actor, role=role, action="search_cases",
                             target_type="cases", detail=f"status={status}",
                             hits=len(rows))
    return {"cases": rows, "count": len(rows)}


@app.get("/access-log")
def access_log(principal: Annotated[dict, Depends(rbac.require("compliance:search"))],
               limit: int = 50):
    """Watching the watchers. Reading this list is itself not logged, because
    that recursion has no end; the writes it shows are the record."""
    rows = conn().execute(
        "SELECT * FROM access_log ORDER BY at DESC LIMIT ?", (min(limit, 200),))
    return {"entries": [dict(r) for r in rows]}


@app.get("/eval/script")
def eval_script(language: str = "en",
                principal: Annotated[dict, Depends(rbac.require("metrics:read"))] = None):
    """The lines to read for the evaluation set, in one language.

    The current evaluation audio is rendered with Piper rather than spoken by
    people, which makes the Hindi, Marathi and code-mixed word error rates
    invalid: a synthesiser transcribing its own output measures the round
    trip, not recognition. This is how the team records real audio.
    """
    import json as _json
    from .config import EVAL_DIR
    items = _json.loads((EVAL_DIR / "utterances.json").read_text())["utterances"]
    lines = [{"id": i["id"], "text": i["text"], "intent": i.get("intent")}
             for i in items if i["language"] == language]
    have = {p.stem for p in (EVAL_DIR / "audio").glob("*.wav")}
    for line in lines:
        line["recorded"] = line["id"] in have
    return {"language": language, "lines": lines, "count": len(lines)}


@app.post("/eval/record/{utterance_id}")
async def eval_record(utterance_id: str,
                      audio: Annotated[UploadFile, File()],
                      principal: Annotated[dict, Depends(rbac.require("enroll"))]):
    """Store one recorded evaluation line.

    This writes into the evaluation set, not into a call. It is synthetic
    data in the sense that matters: the speaker is a team member reading a
    script written for the purpose, not a customer, and the text is already
    in the repository.
    """
    import re as _re
    from .config import EVAL_DIR
    from .pipeline import audio_io
    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,32}", utterance_id):
        raise HTTPException(400, "bad utterance id")
    data = await audio.read()
    try:
        samples = audio_io.decode(data)
    except Exception as exc:                                  # noqa: BLE001
        raise HTTPException(400, f"could not decode that recording: {exc}")
    if samples.size < 1600:                                   # under 0.1 s
        raise HTTPException(400, "that recording is too short to be a sentence")
    target = EVAL_DIR / "audio" / f"{utterance_id}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio_io.to_wav_bytes(samples))
    return {"id": utterance_id, "seconds": round(samples.size / 16000, 2),
            "path": str(target)}


@app.get("/eval/audio/{utterance_id}")
def eval_audio(utterance_id: str,
               principal: Annotated[dict, Depends(rbac.require("metrics:read"))]):
    """Play back a recorded evaluation line.

    Recording without listening is not reviewing. Without this the page
    could capture a clip and give no way to tell whether it had picked up
    the microphone at all.
    """
    import re as _re
    from .config import EVAL_DIR
    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,32}", utterance_id):
        raise HTTPException(400, "bad utterance id")
    path = EVAL_DIR / "audio" / f"{utterance_id}.wav"
    if not path.exists():
        raise HTTPException(404, f"no recording for {utterance_id}")
    return Response(content=path.read_bytes(), media_type="audio/wav")


@app.get("/providers")
def providers(principal: Annotated[dict, Depends(rbac.require("metrics:read"))]):
    """Which speech provider answers for each language, and what it has cost.

    These APIs bill per use, so the meter is on screen rather than discovered
    on an invoice. `leaves_machine` is the part that matters for the honesty
    registry: it says whether the caller's words went anywhere.
    """
    from .pipeline import providers as pv
    return pv.health_report()


# ---------------------------------------------------------------- recordings

@app.post("/session/{session_id}/recording-notice")
def recording_notice(session_id: str, consented: bool,
                     principal: Annotated[dict, Depends(rbac.require("turn:submit"))]):
    """Called when the spoken recording notice has finished.

    Nothing is stored before this runs. Declining purges whatever the call
    already captured rather than only stopping from here (D21).
    """
    try:
        return turn.complete_recording_notice(conn(), session_id, consented)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))


@app.get("/calls/{call_id}/recordings")
def call_recordings(call_id: str,
                    principal: Annotated[dict, Depends(rbac.require("recording:list"))]):
    rows = conn().execute(
        "SELECT recording_id, turn_id, speaker, duration_s, language, sha256,"
        " created_at, retention_until, purged_at FROM recordings"
        " WHERE call_id=? ORDER BY created_at", (call_id,))
    return {"call_id": call_id, "recordings": [dict(r) for r in rows]}


@app.get("/recordings/{recording_id}")
def play_recording(recording_id: str,
                   principal: Annotated[dict, Depends(rbac.require("recording:play"))]):
    """Decrypt and return one recording. Always logged, always ledgered."""
    from .security import recordings
    try:
        audio = recordings.read(conn(), recording_id,
                                actor=principal["sub"], role=principal["role"])
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        # The stored digest did not match. That is a finding, not a 500.
        raise HTTPException(409, str(exc))
    return Response(content=audio, media_type="audio/wav")


# ---------------------------------------------------------------- ledger

@app.post("/ledger/verify")
def ledger_verify(use_checkpoints: bool = True,
                  principal: Annotated[dict, Depends(rbac.require("ledger:verify"))] = None):
    t0 = time.perf_counter()
    out = ledger.verify(conn(), use_checkpoints=use_checkpoints)
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    out["verified_at"] = utcnow().isoformat()
    return out


@app.get("/ledger/export")
def ledger_export(principal: Annotated[dict, Depends(rbac.require("ledger:export"))]):
    """Compliance export: the full chain plus a detached HMAC signature."""
    out = ledger.export(conn())
    out["exported_by"] = principal.get("sub")
    return JSONResponse(out, headers={"Content-Disposition":
                                      'attachment; filename="ledger-export.json"'})


@app.get("/ledger/records")
def ledger_records(limit: int = 200, offset: int = 0,
                   principal: Annotated[dict, Depends(rbac.require("ledger:verify"))] = None):
    rows = conn().execute(
        "SELECT idx, record_id, kind, session_id, ts, prev_hash, hash, sig, payload"
        " FROM ledger ORDER BY idx DESC LIMIT ? OFFSET ?", (limit, offset))
    total = conn().execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]
    return {"total": total, "records": [dict(r) for r in rows]}


# ---------------------------------------------------------------- escalation

@app.get("/handovers")
def handovers(principal: Annotated[dict, Depends(rbac.require("handover:read"))]):
    rows = conn().execute(
        "SELECT handover_id, trace_id, session_id, created_at, reason, status, claimed_by"
        " FROM handovers ORDER BY created_at DESC LIMIT 50")
    return {"handovers": [dict(r) for r in rows]}


@app.post("/agent/handover/{trace_id}")
def claim_handover(trace_id: str,
                   principal: Annotated[dict, Depends(rbac.require("handover:claim"))]):
    row = conn().execute("SELECT * FROM handovers WHERE trace_id=?", (trace_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"no handover for trace {trace_id}")
    agent = principal.get("sub")
    conn().execute("UPDATE handovers SET claimed_by=?, status='claimed' WHERE handover_id=?",
                   (agent, row["handover_id"]))
    conn().commit()
    ledger.append(conn(), "handover_claimed",
                  {"handover_id": row["handover_id"], "trace_id": trace_id, "agent_id": agent},
                  session_id=row["session_id"])
    return {"handover_id": row["handover_id"], "agent_id": agent,
            "packet": json.loads(row["packet"])}


# ---------------------------------------------------------------- observability

@app.get("/metrics")
def metrics(principal: Annotated[dict, Depends(rbac.require("metrics:read"))]):
    """Latency percentiles per stage and decision counters, read off the traces
    rather than a separate metrics pipeline. Prometheus and Grafana are the
    production substitution, recorded in STACK_MAPPING.md."""
    import statistics
    stages = {}
    for name, samples in METRICS["stage_ms"].items():
        ordered = sorted(samples)
        stages[name] = {
            "n": len(ordered),
            "p50_ms": round(statistics.median(ordered), 2),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 2),
            "mean_ms": round(statistics.fmean(ordered), 2)}
    counts = dict(conn().execute(
        "SELECT kind, COUNT(*) FROM ledger GROUP BY kind").fetchall()) if CONN else {}
    return {"turns": METRICS["turns"], "decisions": METRICS["decisions"],
            "stages": stages, "ledger_records_by_kind": counts,
            "uptime_s": round(time.time() - STARTED_AT, 1)}


@app.get("/kb")
def kb_documents(principal: Annotated[dict, Depends(rbac.require("trace:read_own"))]):
    """The policy KB as the dashboard shows it, including superseded versions."""
    from .pipeline import retrieval
    try:
        _, chunks = retrieval._index()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    docs: dict[str, dict] = {}
    for c in chunks:
        key = f"{c['doc_id']}@{c['version']}"
        d = docs.setdefault(key, {"doc_id": c["doc_id"], "version": c["version"],
                                  "title": c["title"], "category": c["category"],
                                  "effective_date": c["effective_date"],
                                  "superseded_by": c["superseded_by"], "sections": []})
        d["sections"].append(c["section"])
    return {"documents": sorted(docs.values(), key=lambda d: (d["doc_id"], d["version"]))}


# ---------------------------------------------------------------- websocket

@app.websocket("/ws/session")
async def ws_session(ws: WebSocket):
    """Audio in, partial transcript and reply out.

    Protocol, deliberately small:
      client -> {"type": "start", "token": "...", "session_id": "..."}
      client -> binary audio frames (16 kHz int16 PCM)
      client -> {"type": "end"}          finalise the utterance and run the turn
      client -> {"type": "text", ...}    the fallback path over the same socket
      server -> {"type": "partial"|"trace"|"reply"|"error", ...}
    """
    await ws.accept()
    buffer = bytearray()
    session_id: str | None = None
    principal: dict | None = None
    try:
        while True:
            message = await ws.receive()
            if "bytes" in message and message["bytes"] is not None:
                buffer.extend(message["bytes"])
                if len(buffer) % (32000 * 2) < 4096:        # roughly every 2 seconds
                    await ws.send_json({"type": "partial",
                                        "buffered_s": round(len(buffer) / 32000, 2)})
                continue
            if "text" not in message or message["text"] is None:
                break
            msg = json.loads(message["text"])
            kind = msg.get("type")

            if kind == "start":
                try:
                    principal = rbac.decode_token(msg.get("token", ""))
                except HTTPException as exc:
                    await ws.send_json({"type": "error", "error": exc.detail})
                    await ws.close()
                    return
                if not rbac.allowed(principal.get("role", ""), "turn:submit"):
                    await ws.send_json({"type": "error", "error": "role may not submit turns"})
                    await ws.close()
                    return
                session_id = msg.get("session_id")
                buffer.clear()
                await ws.send_json({"type": "ready", "session_id": session_id})

            elif kind in ("end", "text"):
                if not principal or not session_id:
                    await ws.send_json({"type": "error", "error": "send start first"})
                    continue
                audio = bytes(buffer) if kind == "end" and buffer else None
                buffer.clear()
                try:
                    t = await asyncio.to_thread(
                        turn.run_turn, conn(), session_id,
                        text=msg.get("text"), audio=audio, otp=msg.get("otp"),
                        confirm=msg.get("confirm"))
                except Exception as exc:                     # noqa: BLE001
                    METRICS["errors"] += 1
                    await ws.send_json({"type": "error", "error": str(exc)})
                    continue
                _record_metrics(t)
                await ws.send_json({"type": "trace", "trace": t.model_dump(mode="json")})
                if t.reply_text:
                    from .pipeline import tts
                    spoken = await asyncio.to_thread(tts.synthesize, t.reply_text,
                                                     t.reply_language)
                    await ws.send_json({"type": "reply", "text": t.reply_text,
                                        "language": t.reply_language,
                                        "voice": spoken["voice"],
                                        "audio_available": spoken["available"]})
                    if spoken["available"]:
                        await ws.send_bytes(spoken["audio"])

            elif kind == "close":
                break
    except WebSocketDisconnect:
        pass
    finally:
        buffer.clear()             # raw audio never outlives the connection
