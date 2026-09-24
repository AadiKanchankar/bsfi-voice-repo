"""A8. Tamper-evident append-only ledger.

    H_i   = SHA256( H_{i-1} || canonical_json(M_i) || t_i )
    sig_i = HMAC-SHA256( key, H_i )

Canonical JSON (sorted keys, fixed separators) is not a detail. If the
serialisation is not byte-identical on replay, verification is
non-deterministic and the ledger proves nothing. Everything here goes through
trace.canonical_json.

Three independent things are checked per record:

  link     prev_hash of record i equals hash of record i-1
  binding  hash of record i equals SHA256(prev_hash || payload || ts)
  sig      HMAC over the hash matches, using a key not stored in the database

`binding` is what catches the demo's beat 10: an UPDATE that changes a payload
field without recomputing anything. `link` and `sig` catch the more determined
attacker who rewrites hashes forward but has no HMAC key.

On complexity, stated honestly because the paper repeats it:
  full verify           O(n)
  checkpoint locate     O(log(n/k)) probes of O(k) each when the corruption
                        extends to the end of the chain (a rewriting attacker),
                        falling back to a scan of the n/k segment anchors for a
                        single isolated row edit. True O(log n) inclusion proof
                        for one record needs the Merkle upgrade in the stretch
                        goals, not a linear chain.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import uuid
from typing import Any, Iterable

from ..config import (LEDGER_CHECKPOINT_INTERVAL, LEDGER_GENESIS_HASH,
                      LEDGER_HMAC_KEY_DEFAULT, LEDGER_HMAC_KEY_ENV)
from ..trace import canonical_json, utcnow


def _key() -> bytes:
    return os.environ.get(LEDGER_HMAC_KEY_ENV, LEDGER_HMAC_KEY_DEFAULT).encode("utf-8")


def compute_hash(prev_hash: str, payload_json: str, ts: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(payload_json.encode("utf-8"))
    h.update(ts.encode("utf-8"))
    return h.hexdigest()


def sign(record_hash: str) -> str:
    return hmac.new(_key(), record_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def head(conn: sqlite3.Connection) -> tuple[int, str]:
    """(index of last record, its hash). (-1, genesis) on an empty chain."""
    row = conn.execute("SELECT idx, hash FROM ledger ORDER BY idx DESC LIMIT 1").fetchone()
    return (row["idx"], row["hash"]) if row else (-1, LEDGER_GENESIS_HASH)


def append(conn: sqlite3.Connection, kind: str, payload: Any,
           session_id: str | None = None, record_id: str | None = None,
           ts: str | None = None) -> dict:
    """Append one record and return its ledger row as a dict."""
    last_idx, prev_hash = head(conn)
    idx = last_idx + 1
    rid = record_id or str(uuid.uuid4())
    timestamp = ts or utcnow().isoformat()
    payload_json = canonical_json(payload)
    h = compute_hash(prev_hash, payload_json, timestamp)
    s = sign(h)
    conn.execute(
        "INSERT INTO ledger (idx, record_id, kind, session_id, payload, ts, prev_hash, hash, sig)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (idx, rid, kind, session_id, payload_json, timestamp, prev_hash, h, s))
    if (idx + 1) % LEDGER_CHECKPOINT_INTERVAL == 0:
        conn.execute("INSERT OR REPLACE INTO ledger_checkpoint (idx, hash) VALUES (?,?)", (idx, h))
    conn.commit()
    return {"idx": idx, "record_id": rid, "kind": kind, "ts": timestamp,
            "prev_hash": prev_hash, "hash": h, "sig": s}


# ---------------------------------------------------------------- verification

def _check_record(row: sqlite3.Row, expected_prev: str) -> str | None:
    """Returns None if the record is intact, else the name of the failed check."""
    if row["prev_hash"] != expected_prev:
        return "link"
    if compute_hash(row["prev_hash"], row["payload"], row["ts"]) != row["hash"]:
        return "binding"
    if not hmac.compare_digest(sign(row["hash"]), row["sig"]):
        return "sig"
    return None


def verify_record(conn: sqlite3.Connection, idx: int) -> dict:
    """Verify one record in place, for a per-row status in the dashboard.

    This checks the three properties a single record can carry on its own:
    that it links to the hash its predecessor actually stores, that its hash
    binds its own payload and timestamp, and that the signature matches.

    It is deliberately not a substitute for `verify`. A record can pass here
    while the chain is broken further back, so the dashboard shows this
    beside a whole-chain result and never instead of one.
    """
    row = conn.execute("SELECT * FROM ledger WHERE idx=?", (idx,)).fetchone()
    if row is None:
        return {"ok": False, "reason": "no such record"}
    if idx == 0:
        prev = LEDGER_GENESIS_HASH
    else:
        before = conn.execute("SELECT hash FROM ledger WHERE idx=?", (idx - 1,)).fetchone()
        if before is None:
            return {"ok": False, "reason": "predecessor missing"}
        prev = before["hash"]
    failed = _check_record(row, prev)
    return {"ok": failed is None, "reason": failed}


def _rows(conn: sqlite3.Connection, lo: int, hi: int) -> Iterable[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ledger WHERE idx >= ? AND idx <= ? ORDER BY idx", (lo, hi))


def _scan(conn: sqlite3.Connection, lo: int, hi: int, anchor: str) -> tuple[dict | None, int, str]:
    """Scan [lo, hi] from `anchor`. Returns (break_info | None, count, last_hash)."""
    prev = anchor
    count = 0
    for row in _rows(conn, lo, hi):
        count += 1
        failed = _check_record(row, prev)
        if failed is not None:
            expected = (prev if failed == "link"
                        else compute_hash(row["prev_hash"], row["payload"], row["ts"]))
            actual = row["prev_hash"] if failed == "link" else row["hash"]
            if failed == "sig":
                expected, actual = sign(row["hash"]), row["sig"]
            return ({"first_broken_index": row["idx"],
                     "broken_record_id": row["record_id"],
                     "broken_check": failed,
                     "expected_hash": expected,
                     "actual_hash": actual,
                     "kind": row["kind"],
                     "session_id": row["session_id"],
                     "ts": row["ts"]}, count, prev)
        prev = row["hash"]
    return (None, count, prev)


def verify_linear(conn: sqlite3.Connection) -> dict:
    """Authoritative O(n) verification from genesis."""
    last_idx, _ = head(conn)
    if last_idx < 0:
        return {"ok": True, "records_checked": 0, "method": "linear", "probes": 0,
                "first_broken_index": None, "broken_record_id": None,
                "expected_hash": None, "actual_hash": None}
    brk, count, _ = _scan(conn, 0, last_idx, LEDGER_GENESIS_HASH)
    out = {"ok": brk is None, "records_checked": count, "method": "linear",
           "probes": count, "total_records": last_idx + 1,
           "first_broken_index": None, "broken_record_id": None,
           "expected_hash": None, "actual_hash": None}
    if brk:
        out.update(brk)
    return out


# ponytail: linear chain with segment anchors. An isolated payload edit that
# touches no hash still costs a full anchor walk to locate, because nothing
# downstream disagrees. Upgrade to a Merkle tree if a regulator ever asks for
# an O(log n) inclusion proof of one record; the verify() signature does not
# change. tests/test_ledger.py::test_isolated_edit_costs_a_full_scan pins this.

def _checkpoints(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT idx, hash FROM ledger_checkpoint ORDER BY idx"))


def verify(conn: sqlite3.Connection, use_checkpoints: bool = True) -> dict:
    """Verify the chain and localise the first break.

    With checkpoints, work is done segment by segment. A binary search over the
    segment anchors runs first, which lands in O(log(n/k)) probes when the
    corruption reaches the end of the chain; if that search reports a clean
    chain but the head does not reconcile, or the located segment turns out
    intact, we fall back to scanning the anchors in order. Either way the answer
    matches verify_linear, which the tests assert on random corruptions.
    """
    last_idx, _ = head(conn)
    if last_idx < 0:
        return verify_linear(conn)
    cps = _checkpoints(conn) if use_checkpoints else []
    if not cps:
        return verify_linear(conn)

    # Segment j covers (anchor_idx[j-1], anchor_idx[j]]; the tail segment runs
    # from the last anchor to the head and has no stored anchor of its own.
    bounds: list[tuple[int, int, str | None]] = []
    prev_idx = -1
    for cp in cps:
        bounds.append((prev_idx + 1, cp["idx"], cp["hash"]))
        prev_idx = cp["idx"]
    if prev_idx < last_idx:
        bounds.append((prev_idx + 1, last_idx, None))

    anchors = [LEDGER_GENESIS_HASH] + [b[2] for b in bounds[:-1]]
    probes = {"n": 0, "records": 0}

    def segment_ok(j: int) -> bool:
        lo, hi, expect = bounds[j]
        brk, count, last_hash = _scan(conn, lo, hi, anchors[j] or LEDGER_GENESIS_HASH)
        probes["n"] += 1
        probes["records"] += count
        return brk is None and (expect is None or last_hash == expect)

    # Fast path: binary search for the first failing segment, correct whenever
    # failure propagates to the end of the chain.
    lo_j, hi_j = 0, len(bounds) - 1
    candidate: int | None = None
    if not segment_ok(hi_j):
        while lo_j < hi_j:
            mid = (lo_j + hi_j) // 2
            if segment_ok(mid):
                lo_j = mid + 1
            else:
                hi_j = mid
        candidate = lo_j
    else:
        # Isolated edit: the tail reconciles, so walk the anchors in order.
        for j in range(len(bounds) - 1):
            if not segment_ok(j):
                candidate = j
                break

    if candidate is None:
        return {"ok": True, "records_checked": probes["records"], "method": "checkpoint",
                "probes": probes["n"], "total_records": last_idx + 1,
                "checkpoint_interval": LEDGER_CHECKPOINT_INTERVAL,
                "first_broken_index": None, "broken_record_id": None,
                "expected_hash": None, "actual_hash": None}

    lo, hi, _ = bounds[candidate]
    brk, count, last_hash = _scan(conn, lo, hi, anchors[candidate] or LEDGER_GENESIS_HASH)
    out = {"ok": False, "records_checked": probes["records"] + count, "method": "checkpoint",
           "probes": probes["n"] + 1, "total_records": last_idx + 1,
           "checkpoint_interval": LEDGER_CHECKPOINT_INTERVAL,
           "segment": [lo, hi],
           "first_broken_index": None, "broken_record_id": None,
           "broken_check": "checkpoint_anchor", "expected_hash": bounds[candidate][2],
           "actual_hash": last_hash}
    if brk:
        out.update(brk)
    return out


def export(conn: sqlite3.Connection) -> dict:
    """Full chain plus a detached signature over the export itself."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM ledger ORDER BY idx")]
    body = {"genesis": LEDGER_GENESIS_HASH, "count": len(rows), "records": rows,
            "exported_at": utcnow().isoformat(),
            "checkpoint_interval": LEDGER_CHECKPOINT_INTERVAL,
            "checkpoints": [dict(c) for c in _checkpoints(conn)]}
    body_json = canonical_json(body)
    return {"export": body,
            "signature": hmac.new(_key(), body_json.encode("utf-8"),
                                  hashlib.sha256).hexdigest(),
            "signature_alg": "HMAC-SHA256"}
