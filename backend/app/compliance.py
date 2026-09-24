"""R2. What a compliance officer can look up, and the record of them doing it.

The lookup this replaces returned `200 {"traces": []}` for an unknown id, a
partial id, a customer id and a typo alike, so nothing a user typed could
ever report failure. See DECISIONS.md D22 for the reproduction.

Three rules hold everywhere in this module:

- **A miss is a miss.** `resolve` returns None rather than an empty result
  set, so the endpoint can answer 404 with what was searched for. An empty
  list means "this exists and has nothing in it", and nothing else.
- **Prefix matching, because the console shows eight characters.** A session
  id is a 36 character UUID that the UI never displays in full. Requiring the
  whole thing made the field unusable during a demo.
- **Looking is an event.** Every search and every drill-down writes to
  `access_log` and to the ledger. An audit trail that does not record its own
  auditors is half a trail.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .security import ledger, recordings

# How many rows a search returns before it starts asking for a narrower query.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


# ---------------------------------------------------------------- audit

def record_access(conn: sqlite3.Connection, *, actor: str, role: str,
                  action: str, target_type: str | None = None,
                  target_id: str | None = None, detail: str | None = None,
                  hits: int | None = None) -> None:
    """One access_log row and one ledger record per look.

    The ledger payload carries no customer identifiers beyond the id that was
    searched for, which the officer already had. It is evidence that a lookup
    happened, not a second copy of the data.
    """
    recordings.log_access(conn, actor=actor, role=role, action=action,
                          target_type=target_type, target_id=target_id,
                          detail=detail)
    ledger.append(conn, "compliance_access", {
        "actor": actor, "role": role, "action": action,
        "target_type": target_type, "target_id": target_id,
        "detail": detail, "hits": hits,
    })


# ---------------------------------------------------------------- resolve

def resolve(conn: sqlite3.Connection, identifier: str) -> dict | None:
    """What kind of thing is this string, if anything.

    One search box, four kinds of identifier, prefix matching on all of them.
    Returns None when nothing matches, which is what lets the caller answer
    404 instead of an empty list.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None
    like = ident + "%"

    row = conn.execute("SELECT call_id FROM calls WHERE call_id=? OR call_id LIKE ?"
                       " ORDER BY started_at DESC LIMIT 1",
                       (ident.upper(), ident.upper() + "%")).fetchone()
    if row:
        return {"kind": "call", "id": row["call_id"]}

    row = conn.execute("SELECT call_id, session_id FROM sessions"
                       " WHERE session_id=? OR session_id LIKE ?"
                       " ORDER BY created_at DESC LIMIT 1", (ident, like)).fetchone()
    if row:
        return {"kind": "session", "id": row["session_id"], "call_id": row["call_id"]}

    row = conn.execute("SELECT customer_id FROM customers"
                       " WHERE customer_id=? OR customer_id LIKE ? LIMIT 1",
                       (ident.upper(), ident.upper() + "%")).fetchone()
    if row:
        return {"kind": "customer", "id": row["customer_id"]}

    row = conn.execute("SELECT case_id FROM cases WHERE case_id=? OR case_id LIKE ?"
                       " LIMIT 1", (ident.upper(), ident.upper() + "%")).fetchone()
    if row:
        return {"kind": "case", "id": row["case_id"]}

    # A mobile number is not an identifier a compliance officer should need,
    # but it is the one a caller states, so it resolves too.
    from .banking.registry import find_by_mobile
    found = find_by_mobile(conn, ident)
    if found:
        return {"kind": "customer", "id": found["customer_id"]}
    return None


# ---------------------------------------------------------------- search

def search_calls(conn: sqlite3.Connection, *, customer_id: str | None = None,
                 date_from: str | None = None, date_to: str | None = None,
                 decision: str | None = None, tier: int | None = None,
                 language: str | None = None, call_id: str | None = None,
                 limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Call summaries, newest first, filtered.

    `decision` and `tier` filter on the turns of a call rather than the call
    itself: a call is interesting because one turn in it was refused or ran at
    tier 3, not because its last turn was.
    """
    where, args = ["1=1"], []
    if customer_id:
        where.append("c.customer_id = ?"); args.append(customer_id.upper())
    if call_id:
        where.append("c.call_id LIKE ?"); args.append(call_id.upper() + "%")
    if date_from:
        where.append("c.started_at >= ?"); args.append(date_from)
    if date_to:
        # Inclusive of the whole day when a bare date is given.
        where.append("c.started_at <= ?")
        args.append(date_to if len(date_to) > 10 else date_to + "T23:59:59")
    if language:
        where.append("(c.language = ? OR EXISTS (SELECT 1 FROM turns t"
                     " WHERE t.call_id = c.call_id AND t.language = ?))")
        args += [language, language]
    if decision == "interrupted":
        # Not a decision but a property of a turn, and the change request
        # lists it alongside them because it is the same question: show me
        # the calls where this happened.
        where.append("EXISTS (SELECT 1 FROM turns t WHERE t.call_id = c.call_id"
                     " AND t.interrupted = 1)")
    elif decision:
        where.append("EXISTS (SELECT 1 FROM turns t WHERE t.call_id = c.call_id"
                     " AND t.decision = ?)"); args.append(decision)
    if tier is not None:
        where.append("EXISTS (SELECT 1 FROM turns t WHERE t.call_id = c.call_id"
                     " AND t.risk_tier >= ?)"); args.append(int(tier))

    rows = conn.execute(
        "SELECT c.call_id, c.customer_id, c.started_at, c.ended_at, c.language,"
        "       c.channel, c.final_state, c.recording_consent,"
        "       cu.name AS customer_name,"
        "       (SELECT COUNT(*) FROM turns t WHERE t.call_id=c.call_id) AS turns,"
        "       (SELECT MAX(t.risk_tier) FROM turns t WHERE t.call_id=c.call_id) AS max_tier,"
        "       (SELECT COUNT(*) FROM recordings r WHERE r.call_id=c.call_id"
        "        AND r.purged_at IS NULL) AS recordings,"
        "       (SELECT COUNT(*) FROM cases cs WHERE cs.call_id=c.call_id) AS cases,"
        "       (SELECT COUNT(*) FROM turns t WHERE t.call_id=c.call_id"
        "        AND t.interrupted=1) AS interrupted"
        "  FROM calls c LEFT JOIN customers cu ON cu.customer_id = c.customer_id"
        f" WHERE {' AND '.join(where)}"
        " ORDER BY c.started_at DESC LIMIT ?",
        (*args, min(int(limit), MAX_LIMIT)))
    return [dict(r) for r in rows]


def recent_calls(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """The list that means nobody has to paste a UUID during a demo."""
    return search_calls(conn, limit=limit)


# ---------------------------------------------------------------- drill-down

def call_detail(conn: sqlite3.Connection, call_id: str) -> dict | None:
    """Everything about one call, assembled from what was stored at the time.

    Nothing here is reconstructed after the fact. The traces are the ones the
    pipeline wrote, the ledger records are the ones it appended, and the
    verification status of each is computed now rather than trusted.
    """
    call = conn.execute("SELECT * FROM calls WHERE call_id=?", (call_id,)).fetchone()
    if call is None:
        return None
    call = dict(call)

    sessions = [dict(r) for r in conn.execute(
        "SELECT session_id, created_at, device_id, verified_at, verified_score,"
        " verified_source, turn_count, withdrawn_at FROM sessions WHERE call_id=?",
        (call_id,))]
    session_ids = [s["session_id"] for s in sessions]

    turns = [dict(r) for r in conn.execute(
        "SELECT * FROM turns WHERE call_id=? ORDER BY turn_id", (call_id,))]

    traces: list[dict] = []
    if session_ids:
        marks = ",".join("?" * len(session_ids))
        traces = [json.loads(r["body"]) for r in conn.execute(
            f"SELECT body FROM traces WHERE session_id IN ({marks})"
            " ORDER BY turn_index", session_ids)]

    recs = [dict(r) for r in conn.execute(
        "SELECT recording_id, turn_id, speaker, duration_s, language, sha256,"
        " created_at, retention_until, purged_at FROM recordings"
        " WHERE call_id=? ORDER BY created_at", (call_id,))]

    cases = [dict(r) for r in conn.execute(
        "SELECT * FROM cases WHERE call_id=? ORDER BY created_at", (call_id,))]

    customer = None
    if call["customer_id"]:
        from .banking.registry import customer_summary
        customer = customer_summary(conn, call["customer_id"])

    return {"call": call, "customer": customer, "sessions": sessions,
            "turns": turns, "traces": traces, "recordings": recs, "cases": cases,
            "ledger": ledger_for_call(conn, call_id, session_ids)}


def ledger_for_call(conn: sqlite3.Connection, call_id: str,
                    session_ids: list[str] | None = None) -> list[dict]:
    """The ledger records belonging to this call, each re-verified now.

    `ledger.session_id` holds a session id for turn records and a call id for
    recording records, because recordings outlive the session that made them.
    Both are matched here so the drill-down shows one chain, not two.
    """
    if session_ids is None:
        session_ids = [r["session_id"] for r in conn.execute(
            "SELECT session_id FROM sessions WHERE call_id=?", (call_id,))]
    keys = [*session_ids, call_id]
    marks = ",".join("?" * len(keys))
    rows = list(conn.execute(
        f"SELECT * FROM ledger WHERE session_id IN ({marks}) ORDER BY idx", keys))

    out = []
    for r in rows:
        check = ledger.verify_record(conn, r["idx"])
        out.append({"idx": r["idx"], "record_id": r["record_id"], "kind": r["kind"],
                    "ts": r["ts"], "hash": r["hash"],
                    "payload": json.loads(r["payload"]),
                    "verified": check["ok"], "reason": check.get("reason")})
    return out


def customer_detail(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    from .banking.registry import customer_summary
    summary = customer_summary(conn, customer_id)
    if summary is None:
        return None
    summary.pop("phone", None)      # masked already, but a summary need not carry it
    return {"customer": summary,
            "calls": search_calls(conn, customer_id=customer_id),
            "cases": [dict(r) for r in conn.execute(
                "SELECT * FROM cases WHERE customer_id=? ORDER BY created_at DESC",
                (customer_id,))]}


def list_cases(conn: sqlite3.Connection, status: str | None = None,
               limit: int = DEFAULT_LIMIT) -> list[dict]:
    sql = ("SELECT cs.*, cu.name AS customer_name FROM cases cs"
           " LEFT JOIN customers cu ON cu.customer_id = cs.customer_id")
    args: list[Any] = []
    if status:
        sql += " WHERE cs.status = ?"; args.append(status)
    sql += " ORDER BY cs.created_at DESC LIMIT ?"
    args.append(min(int(limit), MAX_LIMIT))
    return [dict(r) for r in conn.execute(sql, args)]
