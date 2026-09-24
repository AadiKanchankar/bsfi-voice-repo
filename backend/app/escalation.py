"""R6. What the assistant does after it escalates.

A real helpline does not go silent when it transfers you. Before this, an
escalation created a handover packet and the assistant had nothing further
to say, which is the moment a caller who has just reported fraud is left
listening to nothing.

Four things happen instead, and the order matters because the first is the
one that calms someone down:

1. **Say what is happening, in plain words.** No scores, no tier numbers, no
   internal vocabulary. A case reference, read digit by digit so it can be
   written down, and an honest wait.
2. **Offer the one protective action that is safe to automate.** A temporary
   card freeze during a fraud report reduces harm and is reversible. It is
   the only one enabled, and the whitelist below says why.
3. **Ask the questions the agent would ask anyway**, while the caller waits,
   and attach the answers to the case so nobody has to ask twice.
4. **Stay on the line**: periodic updates, a callback instead of waiting,
   and the tier ratchet still applies, so "while you are holding" does not
   become a window where anything can be automated.

**The tier 3 rule is not being bent here.** Tier 3 forbids automating a
*resolution*: a refund, a reversal, a dispute outcome, a transfer. Freezing
a card resolves nothing. It reduces the harm while the caller waits for the
person who will resolve it, and it can be undone in one step. That
distinction is the whole reason a whitelist exists rather than a flag.
"""
from __future__ import annotations

import sqlite3
import uuid

from .config import PROTECTIVE_ACTIONS, PROTECTIVE_ACTIONS_ENABLED
from .pipeline.speech_text import speech_digits
from .security import ledger
from .trace import utcnow

# Questions worth asking while someone waits, by why they are waiting. Short,
# factual, and exactly what the agent would open with, so the answers save a
# repeat rather than adding an interrogation.
INTAKE = {
    "fraud_report": [
        {"id": "when_noticed", "en": "When did you first notice this?",
         "hi": "आपने यह पहली बार कब देखा?", "mr": "तुम्ही हे पहिल्यांदा कधी पाहिले?"},
        {"id": "amount", "en": "Roughly how much was involved?",
         "hi": "लगभग कितनी राशि थी?", "mr": "अंदाजे किती रक्कम होती?"},
        {"id": "merchant", "en": "Do you know where the transaction was made?",
         "hi": "क्या आप जानते हैं कि लेनदेन कहाँ हुआ?",
         "mr": "व्यवहार कुठे झाला हे तुम्हाला माहीत आहे का?"},
        {"id": "card_present", "en": "Is the card still with you?",
         "hi": "क्या कार्ड अब भी आपके पास है?", "mr": "कार्ड अजूनही तुमच्याकडे आहे का?"},
    ],
    "dispute_txn": [
        {"id": "which_txn", "en": "Which transaction is it?",
         "hi": "कौन सा लेनदेन है?", "mr": "कोणता व्यवहार आहे?"},
        {"id": "why", "en": "What is wrong with it?",
         "hi": "उसमें क्या गड़बड़ है?", "mr": "त्यात काय चूक आहे?"},
        {"id": "contacted_merchant", "en": "Have you contacted the merchant?",
         "hi": "क्या आपने व्यापारी से संपर्क किया?",
         "mr": "तुम्ही व्यापाऱ्याशी संपर्क साधला का?"},
    ],
    "default": [
        {"id": "summary", "en": "Can you tell me a little more while I connect you?",
         "hi": "जब तक मैं जोड़ता हूँ, थोड़ा और बता सकते हैं?",
         "mr": "मी जोडेपर्यंत थोडे अधिक सांगू शकाल का?"},
    ],
}


def case_reference(case_id: str, lang: str = "en") -> str:
    """The reference, said so a caller can write it down.

    Digit by digit, letters spelled. A reference nobody can transcribe is
    not a reference, it is a noise the assistant makes before hanging up.
    """
    from .pipeline.speech_text import spell_code
    return spell_code(case_id.replace("CASE", ""), lang)


def open_case(conn: sqlite3.Connection, *, call_id: str | None,
              customer_id: str | None, reason: str,
              trace_id: str | None = None) -> dict:
    """Create the case the agent will pick up, and tell the caller its number."""
    case_id = f"CASE{uuid.uuid4().hex[:8].upper()}"
    now = utcnow().isoformat()
    conn.execute(
        "INSERT INTO cases (case_id, call_id, customer_id, reason, status,"
        " intake, created_at) VALUES (?,?,?,?,?,?,?)",
        (case_id, call_id, customer_id, reason, "open", None, now))
    conn.commit()
    ledger.append(conn, "case_opened", {
        "case_id": case_id, "call_id": call_id, "customer_ref": customer_id,
        "reason": reason, "trace_id": trace_id, "created_at": now,
    }, session_id=call_id)
    return {"case_id": case_id, "reason": reason, "status": "open",
            "created_at": now}


def intake_questions(reason: str) -> list[dict]:
    return INTAKE.get(reason, INTAKE["default"])


def record_intake(conn: sqlite3.Connection, case_id: str, answers: dict) -> dict:
    """Attach what the caller said to the case.

    Stored as given. These are the caller's own words about their own
    problem, and paraphrasing them into a schema is how the agent ends up
    asking again.
    """
    import json
    row = conn.execute("SELECT intake FROM cases WHERE case_id=?",
                       (case_id,)).fetchone()
    if row is None:
        raise KeyError(f"no case {case_id}")
    existing = json.loads(row["intake"]) if row["intake"] else {}
    existing.update({k: v for k, v in (answers or {}).items() if v})
    conn.execute("UPDATE cases SET intake=? WHERE case_id=?",
                 (json.dumps(existing, ensure_ascii=False), case_id))
    conn.commit()
    ledger.append(conn, "case_intake", {
        "case_id": case_id, "fields": sorted(existing),
    })
    return {"case_id": case_id, "answers": existing}


# ---------------------------------------------------------------- protective

class NotWhitelisted(PermissionError):
    """An action nobody has signed off. Refused rather than attempted."""


def available_actions(reason: str) -> list[dict]:
    """What may be offered for this escalation, and nothing else.

    Reads the whitelist rather than deciding. Adding to it is a change to
    `config.PROTECTIVE_ACTIONS` plus an entry in DECISIONS.md, which is
    deliberately more friction than editing a condition here.
    """
    return [a for a in PROTECTIVE_ACTIONS
            if a["name"] in PROTECTIVE_ACTIONS_ENABLED and reason in a["reasons"]]


def perform_protective_action(conn: sqlite3.Connection, *, name: str,
                              customer_id: str, case_id: str | None,
                              confirmed: bool, call_id: str | None = None) -> dict:
    """Do one whitelisted, reversible thing, only on an explicit yes.

    `confirmed` is not a formality. Every one of these changes something the
    caller will notice, and a caller who said "hmm" is not a caller who said
    yes.
    """
    allowed = {a["name"]: a for a in PROTECTIVE_ACTIONS
               if a["name"] in PROTECTIVE_ACTIONS_ENABLED}
    spec = allowed.get(name)
    if spec is None:
        raise NotWhitelisted(
            f"{name!r} is not an enabled protective action. Enabled: "
            f"{sorted(allowed)}. Adding one needs a DECISIONS entry and "
            f"sign-off, because the tier 3 rule only permits reducing harm, "
            f"never resolving.")
    if not confirmed:
        return {"performed": False, "action": name,
                "reason": "the caller did not confirm"}

    from .banking.mock_core import MockCore
    core = MockCore(conn)
    result: dict = {}
    if name == "freeze_card":
        cards = core.get_cards(customer_id)
        if not cards:
            return {"performed": False, "action": name,
                    "reason": "no card on this customer"}
        result = core.block_card(cards[0]["card_id"])

    now = utcnow().isoformat()
    ledger.append(conn, "protective_action", {
        "action": name, "customer_ref": customer_id, "case_id": case_id,
        "call_id": call_id, "confirmed": True, "reversible": spec["reversible"],
        "result": result, "at": now,
    }, session_id=call_id)
    return {"performed": True, "action": name, "reversible": spec["reversible"],
            "result": result, "at": now}


# ---------------------------------------------------------------- hold

def hold_update(position: int, lang: str = "en") -> dict:
    """Something to say while the caller waits, that is actually true."""
    wait = max(1, position) * 2
    return {
        "queue_position": position, "estimated_wait_minutes": wait,
        "reply": {
            "en": (f"Thank you for holding. You are number {position} in the "
                   f"queue, about {wait} minutes. I can arrange a callback "
                   f"instead if you would prefer."),
            "hi": (f"प्रतीक्षा के लिए धन्यवाद। आप क़तार में {position} नंबर पर हैं, "
                   f"लगभग {wait} मिनट। चाहें तो मैं कॉलबैक की व्यवस्था कर सकता हूँ।"),
            "mr": (f"प्रतीक्षा केल्याबद्दल धन्यवाद. तुम्ही रांगेत {position} क्रमांकावर "
                   f"आहात, अंदाजे {wait} मिनिटे. हवे असल्यास मी कॉलबॅक ठरवू शकतो."),
        }[lang if lang in ("en", "hi", "mr") else "en"],
    }


def offer_callback(conn: sqlite3.Connection, case_id: str, *,
                   call_id: str | None = None, lang: str = "en") -> dict:
    """No agent free. Take the case, give the number, let them go.

    Keeping someone on hold for an agent who is not coming is worse than
    saying so. Any SMS confirmation is SIMULATED and the registry says so.
    """
    conn.execute("UPDATE cases SET status='callback' WHERE case_id=?", (case_id,))
    conn.commit()
    ledger.append(conn, "callback_offered", {
        "case_id": case_id, "call_id": call_id, "channel": "SIMULATED sms",
    }, session_id=call_id)
    spoken = case_reference(case_id, lang)
    return {
        "case_id": case_id, "status": "callback", "sms": "SIMULATED",
        "reply": {
            "en": (f"There is nobody free right now, so I have logged this and "
                   f"someone will call you back. Your reference is {spoken}. "
                   f"Nothing on your account has been changed."),
            "hi": (f"अभी कोई उपलब्ध नहीं है, इसलिए मैंने इसे दर्ज कर लिया है और कोई "
                   f"आपको वापस कॉल करेगा। आपका संदर्भ है {spoken}। आपके खाते में कोई "
                   f"बदलाव नहीं किया गया है।"),
            "mr": (f"आत्ता कोणीही उपलब्ध नाही, म्हणून मी हे नोंदवले आहे आणि कोणीतरी "
                   f"तुम्हाला परत कॉल करेल. तुमचा संदर्भ {spoken} आहे. तुमच्या खात्यात "
                   f"कोणताही बदल केलेला नाही."),
        }[lang if lang in ("en", "hi", "mr") else "en"],
    }


# ---------------------------------------------------------------- agent side

def queue(conn: sqlite3.Connection, status: str = "open") -> list[dict]:
    rows = conn.execute(
        "SELECT cs.*, cu.name AS customer_name FROM cases cs"
        " LEFT JOIN customers cu ON cu.customer_id = cs.customer_id"
        " WHERE cs.status = ? ORDER BY cs.created_at", (status,))
    return [dict(r) for r in rows]


def accept_case(conn: sqlite3.Connection, case_id: str, agent_id: str) -> dict:
    """An agent takes the case and receives everything already known."""
    import json
    row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if row is None:
        raise KeyError(f"no case {case_id}")
    conn.execute("UPDATE cases SET status='assigned', assigned_agent=?"
                 " WHERE case_id=?", (agent_id, case_id))
    conn.commit()
    ledger.append(conn, "case_accepted", {
        "case_id": case_id, "agent_id": agent_id,
    }, session_id=row["call_id"])

    packet = {"case": dict(row), "intake": json.loads(row["intake"] or "{}")}
    if row["call_id"]:
        from . import compliance
        detail = compliance.call_detail(conn, row["call_id"])
        if detail:
            # The agent sees the redacted transcript and the reasoning, not
            # the raw identifiers: the packet is context, not a data dump.
            packet["turns"] = detail["turns"]
            packet["traces"] = [
                {"turn": t.get("turn_index"), "transcript": t.get("transcript"),
                 "intent": t.get("intent"), "risk_tier": t.get("risk_tier"),
                 "risk_components": t.get("risk_components"),
                 "decision": t.get("decision"), "reply": t.get("reply_text")}
                for t in detail["traces"]]
    return packet


def agent_reply(conn: sqlite3.Connection, case_id: str, agent_id: str,
                text: str, lang: str = "en") -> dict:
    """What the agent typed, on its way to being spoken to the caller.

    It goes through the same normaliser and the same voice as everything
    else, so an agent typing an amount gets it read in the Indian system
    without having to know that.
    """
    row = conn.execute("SELECT call_id FROM cases WHERE case_id=?",
                       (case_id,)).fetchone()
    if row is None:
        raise KeyError(f"no case {case_id}")
    ledger.append(conn, "agent_reply", {
        "case_id": case_id, "agent_id": agent_id, "characters": len(text or ""),
        "language": lang,
    }, session_id=row["call_id"])
    return {"case_id": case_id, "agent_id": agent_id, "text": text,
            "language": lang, "spoken": True}


def close_case(conn: sqlite3.Connection, case_id: str, agent_id: str,
               outcome: str) -> dict:
    row = conn.execute("SELECT call_id FROM cases WHERE case_id=?",
                       (case_id,)).fetchone()
    if row is None:
        raise KeyError(f"no case {case_id}")
    now = utcnow().isoformat()
    conn.execute("UPDATE cases SET status='closed', outcome=?, closed_at=?,"
                 " assigned_agent=? WHERE case_id=?",
                 (outcome, now, agent_id, case_id))
    conn.commit()
    ledger.append(conn, "case_closed", {
        "case_id": case_id, "agent_id": agent_id, "outcome": outcome,
        "closed_at": now,
    }, session_id=row["call_id"])
    return {"case_id": case_id, "status": "closed", "outcome": outcome,
            "closed_at": now}
