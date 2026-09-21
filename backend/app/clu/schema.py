"""The contract between the language layer and the banking layer.

Everything the CLU returns is validated against this before anything
downstream sees it. A model that free-associates, invents an intent, or
returns prose instead of JSON is rejected and the turn falls back to the
deterministic classifier. That fallback is the whole reason this is safe to
try: the worst case is the system we already had.

Nothing here carries an authorisation decision. The CLU says what it thinks
the caller MEANT. Whether that may happen is decided by dialogue.py, which
does not know this module exists.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import INTENTS

LanguageTag = Literal["en", "hi", "mr", "code_mixed", "unknown"]


class CLUResult(BaseModel):
    """Structured understanding of one turn."""

    intent: str = Field(description="primary intent, from the fixed intent set")
    sub_intents: list[str] = Field(
        default_factory=list,
        description="further intents in a compound request, most important first")
    entities: dict[str, str | float | int] = Field(
        default_factory=dict,
        description="amount, payee, card_last4, account_last4, cheque_number, product")
    language: LanguageTag = "unknown"
    languages: list[str] = Field(default_factory=list)
    code_mixed: bool = False
    references: list[str] = Field(
        default_factory=list,
        description="what a pronoun or ellipsis in this turn refers to")
    normalized_text: str | None = Field(
        default=None,
        description="the request restated plainly, for the audit trail")
    confidence: float = 0.0
    notes: str | None = Field(default=None, description="one short line, for the trace")

    @field_validator("intent")
    @classmethod
    def _known_intent(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in INTENTS:
            raise ValueError(f"intent {v!r} is not one of the {len(INTENTS)} known intents")
        return v

    @field_validator("sub_intents")
    @classmethod
    def _known_sub_intents(cls, v: list[str]) -> list[str]:
        # Unknown sub-intents are dropped rather than failing the whole turn:
        # they are additive information, not the decision.
        return [s for s in (v or []) if s in INTENTS]

    @field_validator("confidence")
    @classmethod
    def _bounded(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("languages")
    @classmethod
    def _known_languages(cls, v: list[str]) -> list[str]:
        return [x for x in (v or []) if x in ("en", "hi", "mr")]

    @field_validator("notes", "normalized_text")
    @classmethod
    def _bounded_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip()
        return v[:400] if v else None

    @model_validator(mode="after")
    def _coherent(self) -> "CLUResult":
        if self.code_mixed and len(self.languages) < 2:
            # The model said mixed but named one language. Believe the flag,
            # not the list, and let the deterministic tagger fill the spans.
            self.language = "code_mixed"
        if len(self.languages) >= 2:
            self.code_mixed = True
            self.language = "code_mixed"
        self.sub_intents = [s for s in self.sub_intents if s != self.intent]
        return self


# What the provider is told to produce. Kept next to the model it validates so
# the two cannot drift.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "sub_intents": {"type": "array", "items": {"type": "string", "enum": list(INTENTS)}},
        "entities": {"type": "object"},
        "language": {"type": "string", "enum": ["en", "hi", "mr", "code_mixed", "unknown"]},
        "languages": {"type": "array", "items": {"type": "string", "enum": ["en", "hi", "mr"]}},
        "code_mixed": {"type": "boolean"},
        "references": {"type": "array", "items": {"type": "string"}},
        "normalized_text": {"type": "string"},
        "confidence": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["intent", "language", "confidence"],
    "additionalProperties": False,
}
