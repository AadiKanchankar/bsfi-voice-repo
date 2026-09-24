"""The schema, declared once in SQLModel so Alembic can migrate it and so a
PostgreSQL swap is a URL change rather than a rewrite.

Portability rules followed here, because SQLite forgives things PostgreSQL
does not:

- Timestamps are stored as ISO-8601 UTC strings, not native datetimes. SQLite
  has no date type and the existing ledger hashes these strings verbatim, so
  changing the representation would invalidate every chain ever written.
- No `AUTOINCREMENT`, no SQLite-specific defaults, no `sqlite_` pragmas in a
  column definition.
- Binary columns are `LargeBinary`, which maps to BLOB on SQLite and BYTEA on
  PostgreSQL.
- Identifiers are application-generated strings (UUID or a prefixed id), not
  database sequences, so a row keeps its identity across a migration.

**Why both this and raw SQL exist.** The original build used stdlib sqlite3
deliberately: demo beat 10 has a presenter edit a stored row with raw SQL and
the hash chain catches it, and an ORM in the middle was a layer to explain
with nothing to show. Change Request 02 asks for SQLModel plus Alembic, which
wins. The resolution is that these models own the SCHEMA and the migrations,
while the existing query code keeps using plain SQL against the same tables.
Plain SQL is portable; the thing that was not portable was the hand-rolled
`CREATE TABLE` string and the absence of migrations. See DECISIONS.md D20.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Column, Index, LargeBinary, Text, text as sa_text
from sqlmodel import Field, SQLModel


# SQLModel's `default=` is applied in Python when you construct the object. It
# does NOT become a DDL default, so a plain-SQL INSERT that omits the column
# hits NOT NULL. Most of this pipeline writes plain SQL, so every column with
# a default needs a server_default too. `srv` keeps that from being fifteen
# lines of boilerplate.
def srv(value):
    return {"sa_column_kwargs": {"server_default": sa_text(repr(value)
                                 if isinstance(value, str) else str(value))}}


# ---------------------------------------------------------------- ledger


class Ledger(SQLModel, table=True):
    __tablename__ = "ledger"
    idx: int = Field(primary_key=True)          # 0-based position in the chain
    record_id: str = Field(unique=True, index=True)
    kind: str                                   # consent | turn | purge | access | ...
    session_id: Optional[str] = Field(default=None, index=True)
    payload: str = Field(sa_column=Column(Text, nullable=False))
    ts: str
    prev_hash: str
    hash: str
    sig: str


class LedgerCheckpoint(SQLModel, table=True):
    __tablename__ = "ledger_checkpoint"
    idx: int = Field(primary_key=True)
    hash: str


# ---------------------------------------------------------------- calls


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    customer_id: str = Field(primary_key=True)
    name: str
    phone: Optional[str] = None                 # masked at rest, see mask_mobile
    email: Optional[str] = None
    language: Optional[str] = None
    enrolled: int = Field(default=0, **srv(0))
    status: str = Field(default="active", **srv("active"))   # active | suspended | closed
    created_at: Optional[str] = Field(default=None, index=True)


class VoiceEnrollment(SQLModel, table=True):
    """Biometric data. The embedding is encrypted at rest; the audio it came
    from is stored only with explicit separate consent, elsewhere."""
    __tablename__ = "voice_enrollments"
    enrollment_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    embedding: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    nonce: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    model_id: str
    n_clips: int
    quality: Optional[float] = None             # mean pairwise cosine of the clips
    source: str = Field(default="live", **srv("live"))   # live | synthetic
    consent_ref: Optional[str] = None
    audio_consent: int = Field(default=0, **srv(0))   # keep the enrolment clips?
    created_at: str
    revoked_at: Optional[str] = Field(default=None)


class Call(SQLModel, table=True):
    __tablename__ = "calls"
    call_id: str = Field(primary_key=True)
    customer_id: Optional[str] = Field(default=None, index=True)
    consent_ref: Optional[str] = None
    started_at: str = Field(index=True)
    ended_at: Optional[str] = None
    language: Optional[str] = None
    channel: str = Field(default="browser", **srv("browser"))  # browser | text | telephony
    final_state: Optional[str] = Field(default=None, index=True)
    recording_consent: int = Field(default=0, **srv(0))
    notice_completed: int = Field(default=0, **srv(0))  # recording starts only after this


class Turn(SQLModel, table=True):
    __tablename__ = "turns"
    call_id: str = Field(primary_key=True)
    turn_id: int = Field(primary_key=True)
    trace_id: Optional[str] = Field(default=None, index=True)
    state: Optional[str] = None
    decision: Optional[str] = Field(default=None, index=True)
    interrupted: int = Field(default=0, **srv(0))
    # Denormalised from the trace so the dashboard can filter without parsing
    # every blob. The trace stays authoritative; these are a search index.
    risk_tier: Optional[int] = Field(default=None, index=True)
    intent: Optional[str] = None
    language: Optional[str] = Field(default=None, index=True)
    created_at: Optional[str] = None


class Recording(SQLModel, table=True):
    """Encrypted on disk. The row holds the path and the digest, never audio."""
    __tablename__ = "recordings"
    recording_id: str = Field(primary_key=True)
    call_id: str = Field(index=True)
    turn_id: Optional[int] = None
    speaker: str                                # customer | assistant | agent
    path: str                                   # encrypted file, AES-256-GCM
    sha256: str                                 # digest of the PLAINTEXT audio
    duration_s: Optional[float] = None
    language: Optional[str] = None
    consent_ref: Optional[str] = None
    created_at: str
    retention_until: str = Field(index=True)
    purged_at: Optional[str] = None


class Case(SQLModel, table=True):
    __tablename__ = "cases"
    case_id: str = Field(primary_key=True)
    call_id: Optional[str] = Field(default=None, index=True)
    customer_id: Optional[str] = Field(default=None, index=True)
    reason: str
    status: str = Field(default="open", index=True, **srv("open"))  # open | assigned | closed
    intake: Optional[str] = Field(default=None, sa_column=Column(Text))
    assigned_agent: Optional[str] = None
    outcome: Optional[str] = None
    created_at: str
    closed_at: Optional[str] = None


class Agent(SQLModel, table=True):
    __tablename__ = "agents"
    agent_id: str = Field(primary_key=True)
    name: str
    role: str = Field(default="agent", **srv("agent"))


class AccessLog(SQLModel, table=True):
    """Who looked at what. Compliance searches and recording playback are
    themselves auditable events; watching the watchers is part of the story."""
    __tablename__ = "access_log"
    access_id: str = Field(primary_key=True)
    actor: str = Field(index=True)
    role: Optional[str] = None
    action: str                                 # search | view_call | play_recording
    target_type: Optional[str] = None
    target_id: Optional[str] = Field(default=None, index=True)
    detail: Optional[str] = None
    at: str = Field(index=True)


# ---------------------------------------------------------------- existing


class Session(SQLModel, table=True):
    __tablename__ = "sessions"
    session_id: str = Field(primary_key=True)
    call_id: Optional[str] = Field(default=None, index=True)
    customer_id: Optional[str] = None
    consent_ref: Optional[str] = None
    created_at: str
    device_id: Optional[str] = None
    voice_clip: Optional[str] = None
    tier_floor: int = Field(default=0, **srv(0))
    clean_turns: int = Field(default=0, **srv(0))
    verified_at: Optional[str] = None
    verified_score: Optional[float] = None
    verified_spoof: Optional[float] = None
    verified_source: Optional[str] = None
    verified_turns: int = Field(default=0, **srv(0))
    turn_count: int = Field(default=0, **srv(0))
    withdrawn_at: Optional[str] = None


class Consent(SQLModel, table=True):
    __tablename__ = "consents"
    consent_ref: str = Field(primary_key=True)
    session_id: str = Field(index=True)
    purpose: str
    retention_days: int
    granted_at: str
    withdrawn_at: Optional[str] = None
    languages: Optional[str] = None
    recording: int = Field(default=0, **srv(0))   # did they agree to be recorded


class Trace(SQLModel, table=True):
    __tablename__ = "traces"
    trace_id: str = Field(primary_key=True)
    session_id: str = Field(index=True)
    turn_index: int
    created_at: str
    body: str = Field(sa_column=Column(Text, nullable=False))


class Vault(SQLModel, table=True):
    """Token to raw identifier, encrypted per session."""
    __tablename__ = "vault"
    session_id: str = Field(primary_key=True)
    token: str = Field(primary_key=True)
    pii_type: str
    nonce: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    ciphertext: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class Speaker(SQLModel, table=True):
    """The live verification embedding. Kept for query speed; the durable
    record of an enrolment is voice_enrollments."""
    __tablename__ = "speakers"
    customer_id: str = Field(primary_key=True)
    embedding: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    n_clips: int
    source: str
    enrolled_at: str


class Account(SQLModel, table=True):
    __tablename__ = "accounts"
    account_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    account_number: str
    account_type: str
    balance: float
    ifsc: Optional[str] = None
    branch: Optional[str] = None


class Card(SQLModel, table=True):
    __tablename__ = "cards"
    card_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    card_number: str
    card_type: str
    status: str = Field(default="active", **srv("active"))
    daily_limit: float = Field(default=50000, **srv(50000))


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"
    txn_id: str = Field(primary_key=True)
    account_id: str = Field(index=True)
    ts: str
    amount: float
    direction: str
    description: str
    channel: Optional[str] = None


class Payee(SQLModel, table=True):
    __tablename__ = "payees"
    payee_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    name: str
    account_number: str
    ifsc: Optional[str] = None
    added_at: Optional[str] = None


class Cheque(SQLModel, table=True):
    __tablename__ = "cheques"
    cheque_number: str = Field(primary_key=True)
    account_id: str = Field(index=True)
    amount: float
    status: str
    presented_on: Optional[str] = None


class Branch(SQLModel, table=True):
    __tablename__ = "branches"
    ifsc: str = Field(primary_key=True)
    name: str
    city: str
    address: Optional[str] = None


class Holding(SQLModel, table=True):
    __tablename__ = "holdings"
    holding_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    kind: str
    name: str
    units: float
    avg_cost: float
    last_price: float
    as_of: str


class Sip(SQLModel, table=True):
    __tablename__ = "sips"
    sip_id: str = Field(primary_key=True)
    customer_id: str = Field(index=True)
    fund: str
    amount: float
    day_of_month: int
    started_on: str
    status: str = Field(default="active", **srv("active"))


class Handover(SQLModel, table=True):
    __tablename__ = "handovers"
    handover_id: str = Field(primary_key=True)
    trace_id: str = Field(index=True)
    session_id: str
    created_at: str
    reason: str
    packet: str = Field(sa_column=Column(Text, nullable=False))
    claimed_by: Optional[str] = None
    status: str = Field(default="queued", **srv("queued"))


Index("ix_txn_account_ts", Transaction.__table__.c.account_id,
      Transaction.__table__.c.ts.desc())
