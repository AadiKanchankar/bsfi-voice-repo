"""The prompt, versioned and kept small.

PROMPT_VERSION goes into every trace and every ledger record. A change in
behaviour six months from now has to be attributable to a specific prompt or
the audit trail is decorative.

Size is a feature, not tidiness. Groq's free tier caps input tokens per
minute, and the first version of this file was 758 tokens a call, which
allowed nine calls a minute and rate-limited two thirds of an evaluation run.
The examples that survive are the two failure modes a small model actually
gets wrong without them: compound requests and follow-ups.
"""
from __future__ import annotations

import json

from ..config import INTENTS

PROMPT_VERSION = "clu-v2-compact"

SYSTEM = """Convert what a bank customer said into JSON. Do not answer them or \
decide anything.

They speak English, Hindi, Marathi or a mix, and Indic languages are often in \
Latin letters ("mera balance kitna hai"). Mixing is normal, not an error.

- intent: exactly one from the list given. Two asks: the more consequential \
is intent, the other goes in sub_intents.
- Use the conversation to resolve a follow-up, and say what it points at in \
references.
- languages: every language present. code_mixed if more than one.
- entities: only what they said. Never invent an amount, name or account.
- confidence: how sure you are of intent.
- Cannot tell? out_of_scope, low confidence. Guessing is worse.

Output one JSON object. No fence, no commentary."""


def build_user_prompt(transcript: str, context: list[dict] | None = None) -> str:
    """The turn, plus a bounded slice of what came before it."""
    parts = [f"intents: {','.join(INTENTS)}"]
    if context:
        lines = []
        for turn in context:
            said = turn.get("transcript", "")
            got = turn.get("intent")
            lines.append(f"- {said}" + (f" [{got}]" if got else ""))
        parts.append("earlier, oldest first:\n" + "\n".join(lines))
    parts.append(f"said: {transcript}")
    return "\n".join(parts)


def example_messages() -> list[dict]:
    """Two shots, for the two things a small model gets wrong without them."""
    compact = {"separators": (",", ":"), "ensure_ascii": False}
    return [
        {"role": "user", "content": build_user_prompt(
            "Mera balance kitna hai, and last three transactions bhi bata do")},
        {"role": "assistant", "content": json.dumps({
            "intent": "get_balance", "sub_intents": ["mini_statement"],
            "entities": {}, "language": "code_mixed", "languages": ["hi", "en"],
            "code_mixed": True, "references": [], "confidence": 0.93}, **compact)},
        {"role": "user", "content": build_user_prompt(
            "aur uske pehle wali?",
            [{"transcript": "last transaction dikhao", "intent": "mini_statement"}])},
        {"role": "assistant", "content": json.dumps({
            "intent": "mini_statement", "sub_intents": [], "entities": {},
            "language": "hi", "languages": ["hi"], "code_mixed": False,
            "references": ["the transaction before the one just listed"],
            "confidence": 0.88}, **compact)},
    ]
