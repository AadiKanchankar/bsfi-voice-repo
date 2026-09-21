"""ComplianceTrace: the spine.

One trace per turn, threaded through every stage. Stages append, never
overwrite. At the end of the turn the trace is redacted, canonicalised, hashed
and appended to the ledger.

The rule this file exists to enforce: no stage may influence a decision with a
number that is not in the trace. A reviewer must be able to recompute the
decision from the trace alone, with no access to the process that produced it.
tests/test_trace_recompute.py asserts exactly that for the risk score.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .capabilities import CapabilityStatus, status_of

Decision = Literal["automated", "refused", "escalated"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(obj: Any) -> str:
    """Sorted keys, fixed separators, no ASCII escaping surprises.

    The ledger hashes this string. If canonicalisation is not deterministic the
    whole chain is worthless, so every hash in the system goes through here.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


class StageRecord(BaseModel):
    stage: str
    started_at: datetime
    duration_ms: float
    inputs_digest: str            # sha256 of the stage input, never the input
    outputs: dict = {}
    confidence: float | None = None
    model_id: str | None = None
    capability: CapabilityStatus = "SIMULATED"
    notes: str | None = None


class LanguageSpan(BaseModel):
    lang: str
    start_word: int
    end_word: int                 # exclusive
    text: str
    confidence: float


class RetrievedPassage(BaseModel):
    doc_id: str
    version: str
    section: str
    effective_date: str
    score: float
    mmr_score: float | None = None
    text: str


class AuthOutcome(BaseModel):
    method: str                   # "none" | "speaker" | "speaker+otp"
    speaker_score: float | None = None      # raw cosine
    spoof_score: float | None = None        # 1.0 = bona fide
    s_verify: float | None = None           # s_cos * spoof_score, feeds risk
    threshold: float | None = None
    passed: bool = False
    otp_required: bool = False
    otp_passed: bool | None = None
    readback_text: str | None = None
    readback_confirmed: bool | None = None
    reason: str | None = None


class ComplianceTrace(BaseModel):
    trace_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    turn_index: int
    consent_ref: UUID
    created_at: datetime = Field(default_factory=utcnow)

    stages: list[StageRecord] = []
    transcript: str | None = None            # redacted before persistence
    language_spans: list[LanguageSpan] = []
    code_mix_index: float | None = None
    dominant_language: str | None = None

    intent: str | None = None
    intent_confidence: float | None = None
    slots: dict = {}
    # Filled by the optional CLU layer. `clu_source` says which reading the
    # turn actually used, so an auditor can tell a model-influenced decision
    # from a purely deterministic one at a glance.
    clu_source: Literal["baseline", "clu"] | None = None
    sub_intents: list[str] = []
    references: list[str] = []
    normalized_text: str | None = None

    retrieved: list[RetrievedPassage] = []
    retrieval_max_score: float | None = None
    retrieval_floor: float | None = None

    asr_confidence: float | None = None
    retrieval_confidence: float | None = None
    fused_confidence: float | None = None
    fusion_weights: dict = {}

    risk_score: float | None = None
    risk_tier: int | None = None
    risk_components: dict = {}      # every term of R, raw and weighted
    tier_overridden: bool = False
    tier_ratcheted: bool = False
    tau_required: float | None = None

    auth: AuthOutcome | None = None
    decision: Decision | None = None
    decision_reason: str | None = None
    action_taken: str | None = None
    action_result: dict = {}
    reply_text: str | None = None
    reply_language: str | None = None
    agent_id: str | None = None
    handover_packet_ref: str | None = None

    pii_tokens: dict = {}           # token -> type only, never the raw value
    redacted: bool = False

    def stage(self, name: str, inputs: Any, *, component: str | None = None):
        """Context manager that times a stage and appends its record.

        Usage:
            with trace.stage("asr", audio_bytes, component="asr") as rec:
                rec.outputs = {...}
                rec.confidence = 0.9
        """
        return _StageCtx(self, name, inputs, component or name)

    def stage_named(self, name: str) -> StageRecord | None:
        for s in self.stages:
            if s.stage == name:
                return s
        return None

    def total_ms(self) -> float:
        return sum(s.duration_ms for s in self.stages)

    def uses_simulated(self) -> list[str]:
        return [s.stage for s in self.stages if s.capability == "SIMULATED"]


class _StageCtx:
    def __init__(self, trace: ComplianceTrace, name: str, inputs: Any, component: str):
        self.trace, self.name, self.inputs, self.component = trace, name, inputs, component
        self.record: StageRecord | None = None

    def __enter__(self) -> StageRecord:
        self._t0 = time.perf_counter()
        self.record = StageRecord(
            stage=self.name,
            started_at=utcnow(),
            duration_ms=0.0,
            inputs_digest=_input_digest(self.inputs),
            capability=status_of(self.component),
        )
        return self.record

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.record is not None
        self.record.duration_ms = (time.perf_counter() - self._t0) * 1000.0
        if exc is not None:
            self.record.notes = f"stage raised {exc_type.__name__}: {exc}"
        self.trace.stages.append(self.record)
        return False   # never swallow


def _input_digest(inputs: Any) -> str:
    """Hash of the stage input. Bytes are hashed directly so audio never lands
    in the trace; anything else goes through canonical JSON."""
    if isinstance(inputs, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(inputs)).hexdigest()
    return digest(inputs)
