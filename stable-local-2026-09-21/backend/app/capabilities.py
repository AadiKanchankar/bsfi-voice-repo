"""The honesty registry: the single source of truth for what is real here.

A panel member who asks "is that actually working, or is it faked?" should get
the answer off the screen, not from a hedge. Every component declares itself
REAL, BASELINE or SIMULATED, the pipeline stamps its own status onto each trace
stage, and the dashboard renders it.

REAL      - a genuine implementation of the thing named.
BASELINE  - a real but deliberately simpler method than the paper's target.
SIMULATED - not implemented, stands in for an external system.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

CapabilityStatus = Literal["REAL", "BASELINE", "SIMULATED"]


class Capability(BaseModel):
    status: CapabilityStatus
    implementation: str
    note: str | None = None


CAPABILITIES: dict[str, Capability] = {
    "asr": Capability(
        status="REAL", implementation="faster-whisper base int8",
        note="not fine-tuned on banking audio; the measured entity error rate is the "
             "baseline a fine-tuned model must beat. At the `base` size it sometimes "
             "writes Hindi in Perso-Arabic script rather than Devanagari; `small` does "
             "not, and BFSI_ASR_MODEL selects it."),
    "vad": Capability(
        status="REAL", implementation="silero-vad v5 ONNX"),
    "langid": Capability(
        status="REAL", implementation="Viterbi-smoothed per-word posteriors",
        note="word posteriors come from a lexicon and script prior, not a trained LID "
             "head. Perso-Arabic script is mapped to the Hindi state, because that is "
             "what the base ASR emits for Hindi speech."),
    "nlu": Capability(
        status="REAL", implementation="MiniLM embeddings + logistic-regression head, seeded data"),
    "slots": Capability(
        status="REAL", implementation="rule-based extraction, Indian numbering words"),
    "retrieval": Capability(
        status="REAL", implementation="MiniLM + cosine + MMR over versioned policy KB"),
    "tts": Capability(
        status="REAL", implementation="Kokoro-82M ONNX, Piper as automatic fallback",
        note="Hindi and Marathi replies are written in Devanagari: both engines "
             "phonemise from script, so a romanised reply is read with English vowels. "
             "There is no Marathi voice in either engine, so Marathi is spoken with the "
             "Hindi one, which is phonetically close for Devanagari text."),
    "speaker_verify": Capability(
        status="REAL", implementation="ECAPA-TDNN pretrained, live voice check with a TTL",
        note="a check is evidence about who is speaking now, so it expires after five "
             "minutes or five turns. The seeded-clip fallback for a dead microphone is "
             "reported as SIMULATED on the turns it carries, because it demonstrates the "
             "mechanism rather than checking a speaker."),
    "antispoof": Capability(
        status="BASELINE", implementation="LFCC + GMM log-likelihood ratio",
        note="not a trained AASIST countermeasure; classical baseline only"),
    "core_banking": Capability(
        status="SIMULATED", implementation="in-process mock service, synthetic accounts"),
    "otp": Capability(
        status="SIMULATED", implementation="fixed demo code, no SMS gateway"),
    "agent_console": Capability(
        status="SIMULATED", implementation="handover queue in the dashboard, no human on the other end"),
    "ledger": Capability(
        status="REAL", implementation="SHA-256 hash chain + HMAC-SHA-256 signatures + checkpoints"),
    "pii": Capability(
        status="REAL", implementation="regex + Luhn + Verhoeff + spoken-digit recovery"),
    "crypto": Capability(
        status="REAL", implementation="AES-256-GCM at rest for the PII vault"),
    "rbac": Capability(
        status="REAL", implementation="signed JWT, four roles",
        note="demo-scale; the production design names Keycloak and OAuth 2.0"),
}


def status_of(component: str) -> CapabilityStatus:
    """Status for a component, used to stamp trace stages. Unknown means SIMULATED.

    Defaulting an unregistered component to SIMULATED is deliberate: forgetting to
    register something should understate the system, never overstate it.
    """
    cap = CAPABILITIES.get(component)
    return cap.status if cap else "SIMULATED"


def registry_dict() -> dict:
    return {k: v.model_dump() for k, v in CAPABILITIES.items()}
