"""SQLite access, stdlib sqlite3 only.

Why no ORM: the whole point of beat 10 is that a presenter edits a stored row
with raw SQL and the chain catches it. An ORM between us and the bytes would
add a layer to explain and nothing to the demo. See docs/STACK_MAPPING.md.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, RUNTIME_DIR, VAULT_DIR

SCHEMA = """
PRAGMA journal_mode=WAL;
-- synchronous=NORMAL is the documented safe pairing with WAL: commits stop
-- fsyncing, which on this hardware is the difference between 0.4 s and 0.02 ms
-- per ledger append. A power loss can lose the last few commits but cannot
-- corrupt the chain, and the demo appends thousands of records.
PRAGMA synchronous=NORMAL;

-- ---------------------------------------------------------------- ledger
CREATE TABLE IF NOT EXISTS ledger (
  idx         INTEGER PRIMARY KEY,      -- 0-based position in the chain
  record_id   TEXT NOT NULL UNIQUE,
  kind        TEXT NOT NULL,            -- consent | turn | purge | handover | admin
  session_id  TEXT,
  payload     TEXT NOT NULL,            -- canonical JSON of the record body
  ts          TEXT NOT NULL,            -- ISO-8601 UTC, part of the hash preimage
  prev_hash   TEXT NOT NULL,
  hash        TEXT NOT NULL,
  sig         TEXT NOT NULL             -- HMAC-SHA256(key, hash)
);

CREATE TABLE IF NOT EXISTS ledger_checkpoint (
  idx   INTEGER PRIMARY KEY,            -- index of the last record in the segment
  hash  TEXT NOT NULL
);

-- ---------------------------------------------------------------- sessions
CREATE TABLE IF NOT EXISTS sessions (
  session_id   TEXT PRIMARY KEY,
  customer_id  TEXT,
  consent_ref  TEXT,
  created_at   TEXT NOT NULL,
  device_id    TEXT,
  voice_clip   TEXT,                          -- seeded clip used for text-mode verification
  tier_floor   INTEGER NOT NULL DEFAULT 0,   -- the session tier ratchet
  clean_turns  INTEGER NOT NULL DEFAULT 0,   -- consecutive turns raising no escalation
  verified_at    TEXT,                       -- last successful live voice check
  verified_score REAL,
  verified_spoof REAL,
  verified_source TEXT,
  verified_turns INTEGER NOT NULL DEFAULT 0, -- turns spent against that check
  turn_count   INTEGER NOT NULL DEFAULT 0,
  withdrawn_at TEXT
);

CREATE TABLE IF NOT EXISTS consents (
  consent_ref    TEXT PRIMARY KEY,
  session_id     TEXT NOT NULL,
  purpose        TEXT NOT NULL,
  retention_days INTEGER NOT NULL,
  granted_at     TEXT NOT NULL,
  withdrawn_at   TEXT,
  languages      TEXT
);

CREATE TABLE IF NOT EXISTS traces (
  trace_id    TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  turn_index  INTEGER NOT NULL,
  created_at  TEXT NOT NULL,
  body        TEXT NOT NULL            -- redacted ComplianceTrace JSON
);

-- PII vault: one row per token, ciphertext only. Held apart from `traces`
-- so that reading the transcript store never yields an identifier.
CREATE TABLE IF NOT EXISTS vault (
  session_id TEXT NOT NULL,
  token      TEXT NOT NULL,
  pii_type   TEXT NOT NULL,
  nonce      BLOB NOT NULL,
  ciphertext BLOB NOT NULL,
  PRIMARY KEY (session_id, token)
);

-- ---------------------------------------------------------------- mock core banking
CREATE TABLE IF NOT EXISTS customers (
  customer_id TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  phone       TEXT,
  email       TEXT,
  language    TEXT,
  enrolled    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id     TEXT PRIMARY KEY,
  customer_id    TEXT NOT NULL,
  account_number TEXT NOT NULL,
  account_type   TEXT NOT NULL,
  balance        REAL NOT NULL,
  ifsc           TEXT,
  branch         TEXT
);

CREATE TABLE IF NOT EXISTS cards (
  card_id     TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  card_number TEXT NOT NULL,           -- Luhn-valid synthetic
  card_type   TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',
  daily_limit REAL NOT NULL DEFAULT 50000
);

CREATE TABLE IF NOT EXISTS transactions (
  txn_id      TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL,
  ts          TEXT NOT NULL,
  amount      REAL NOT NULL,
  direction   TEXT NOT NULL,           -- debit | credit
  description TEXT NOT NULL,
  channel     TEXT
);

CREATE TABLE IF NOT EXISTS payees (
  payee_id    TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  name        TEXT NOT NULL,
  account_number TEXT NOT NULL,
  ifsc        TEXT,
  added_at    TEXT
);

CREATE TABLE IF NOT EXISTS cheques (
  cheque_number TEXT PRIMARY KEY,
  account_id    TEXT NOT NULL,
  amount        REAL NOT NULL,
  status        TEXT NOT NULL,
  presented_on  TEXT
);

CREATE TABLE IF NOT EXISTS branches (
  ifsc   TEXT PRIMARY KEY,
  name   TEXT NOT NULL,
  city   TEXT NOT NULL,
  address TEXT
);

-- ---------------------------------------------------------------- speaker enrolment
CREATE TABLE IF NOT EXISTS speakers (
  customer_id TEXT PRIMARY KEY,
  embedding   BLOB NOT NULL,           -- float32 ECAPA mean embedding, L2-normalised
  n_clips     INTEGER NOT NULL,
  source      TEXT NOT NULL,           -- 'synthetic' | 'live'
  enrolled_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- escalation queue
CREATE TABLE IF NOT EXISTS handovers (
  handover_id TEXT PRIMARY KEY,
  trace_id    TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  reason      TEXT NOT NULL,
  packet      TEXT NOT NULL,
  claimed_by  TEXT,
  status      TEXT NOT NULL DEFAULT 'queued'
);

CREATE INDEX IF NOT EXISTS ix_traces_session ON traces(session_id);
CREATE INDEX IF NOT EXISTS ix_txn_account ON transactions(account_id, ts DESC);
CREATE INDEX IF NOT EXISTS ix_ledger_session ON ledger(session_id);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(path: Path | None = None) -> sqlite3.Connection:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def tx(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
