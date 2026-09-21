"""Provider abstraction.

The banking pipeline calls `understand_turn`. It does not know, and must not
learn, whether that reached a model on this laptop or a server somewhere.
Swapping providers is a config change.

Providers here:

  null        disabled. understand_turn returns nothing and the deterministic
              classifier decides alone. This is the default, so a clone of
              this repository behaves exactly like the frozen snapshot until
              someone opts in.
  mock        deterministic, offline, no model. Used by the tests so the CLU
              plumbing is testable without a GPU, a download or a key.
  ollama      a local model over Ollama's HTTP API. Keeps the project's
              offline and data-residency claims intact.
  openai      any OpenAI-compatible chat completions endpoint: Groq, OpenRouter,
              Together, a local vLLM, Gemini's compatibility layer. Needs a key
              and sends the transcript off the machine, which the capability
              registry and the trace both record.

On residency: the synopsis argues this system can run inside a bank's
perimeter. A hosted provider breaks that, so `leaves_machine` is part of the
provider contract and ends up in the trace rather than in a footnote.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
from dataclasses import dataclass, field
from typing import Protocol

from ..config import (CLU_MAX_BACKOFF_S, CLU_MAX_RETRIES, CLU_MAX_TOKENS,
                      CLU_MODEL, CLU_PROVIDER, CLU_TEMPERATURE, CLU_TIMEOUT_S,
                      LLM_API_BASE, LLM_API_KEY_ENV)
from .prompt import PROMPT_VERSION, SYSTEM, build_user_prompt, example_messages


# Cloudflare fronts several of these APIs and blocks urllib's default
# User-Agent outright: the response is a 403 with "error code: 1010", which
# reads exactly like a rejected key and is not one. Any ordinary agent string
# passes. Worth an hour of someone's life, so it is written down.
USER_AGENT = "bfsi-voice-assistant/0.1 (compliance-aware voice assistant)"


@dataclass
class ProviderReply:
    """What a provider hands back, before schema validation."""
    text: str
    model: str
    provider: str
    latency_ms: float
    leaves_machine: bool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str
    leaves_machine: bool

    def complete(self, transcript: str, context: list[dict] | None) -> ProviderReply: ...
    def available(self) -> bool: ...


# ---------------------------------------------------------------- null

class NullProvider:
    name = "null"
    leaves_machine = False

    def available(self) -> bool:
        return False

    def complete(self, transcript, context):
        return ProviderReply("", "none", self.name, 0.0, False,
                             error="CLU is disabled (BFSI_CLU_PROVIDER=null)")


# ---------------------------------------------------------------- mock

_NUM = re.compile(r"\b(\d[\d,]*)\b")


class MockProvider:
    """Offline stand-in with no model behind it.

    It exists so the plumbing, the schema, the router, the trace wiring and
    the safety floor are all testable and all tested, on a machine with no
    LLM at all. It is registered SIMULATED and it is not an evaluation
    baseline: `make clu-eval` refuses to report numbers from it.
    """
    name = "mock"
    leaves_machine = False

    def available(self) -> bool:
        return True

    def complete(self, transcript, context):
        t0 = time.perf_counter()
        low = (transcript or "").lower()
        hi_markers = ("mera", "kitna", "batao", "bata", "karo", "chahiye", "hai", "bhi",
                      "kar", "do", "mujhe")
        mr_markers = ("majha", "majhya", "kiti", "sanga", "aahe", "aahet", "kara")
        langs = []
        if re.search(r"[a-z]", low) and any(w in low.split() for w in
                                            ("the", "my", "what", "is", "and", "please",
                                             "balance", "card", "show", "last")):
            langs.append("en")
        if any(w in low.split() for w in hi_markers):
            langs.append("hi")
        if any(w in low.split() for w in mr_markers):
            langs.append("mr")
        langs = langs or ["en"]

        def has(*words):
            return any(w in low for w in words)

        intent, subs = "out_of_scope", []
        if has("balance", "kitna hai", "kiti aahe"):
            intent = "get_balance"
        if has("transaction", "statement", "vyavhar", "len den"):
            if intent == "get_balance":
                subs = ["mini_statement"]
            else:
                intent = "mini_statement"
        if has("block", "band kar", "band kara"):
            intent = "block_card"
        if has("fraud", "fasavnuk", "dhokha"):
            intent = "fraud_report"
        if has("transfer", "bhej", "pathav", "send money"):
            intent = "fund_transfer"
        if has("interest rate", "vyajdar", "byaj", "loan ka rate"):
            intent = "product_info"
        if has("ifsc", "branch", "shakha"):
            intent = "branch_ifsc"

        entities = {}
        m = _NUM.search(transcript or "")
        if m and intent in ("fund_transfer", "limit_change"):
            entities["amount"] = float(m.group(1).replace(",", ""))

        payload = {
            "intent": intent, "sub_intents": subs, "entities": entities,
            "language": "code_mixed" if len(langs) > 1 else langs[0],
            "languages": langs, "code_mixed": len(langs) > 1,
            "references": [], "normalized_text": None,
            "confidence": 0.8 if intent != "out_of_scope" else 0.3,
            "notes": "mock provider, keyword rules, not a language model",
        }
        return ProviderReply(json.dumps(payload), "mock-rules", self.name,
                             (time.perf_counter() - t0) * 1000, False)


# ---------------------------------------------------------------- ollama

class OllamaProvider:
    """A model running on this machine. Preserves data residency."""
    name = "ollama"
    leaves_machine = False

    def __init__(self, model: str | None = None, base: str | None = None):
        self.model = model or CLU_MODEL
        self.base = (base or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")

    def available(self) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.base}/api/tags", timeout=2):
                return True
        except Exception:                                   # noqa: BLE001
            return False

    def complete(self, transcript, context):
        import urllib.request
        messages = ([{"role": "system", "content": SYSTEM}] + example_messages()
                    + [{"role": "user", "content": build_user_prompt(transcript, context)}])
        body = json.dumps({
            "model": self.model, "messages": messages, "stream": False,
            "format": "json",
            "options": {"temperature": CLU_TEMPERATURE, "num_predict": CLU_MAX_TOKENS},
        }).encode()
        req = urllib.request.Request(
            f"{self.base}/api/chat", data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=CLU_TIMEOUT_S) as r:
                data = json.loads(r.read())
        except Exception as exc:                            # noqa: BLE001
            return ProviderReply("", self.model, self.name,
                                 (time.perf_counter() - t0) * 1000, False, error=str(exc))
        return ProviderReply(
            data.get("message", {}).get("content", ""), self.model, self.name,
            (time.perf_counter() - t0) * 1000, False,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"))


# ---------------------------------------------------------------- openai-compatible

def _retry_after(exc, detail: str, attempt: int) -> float:
    """How long to wait after a 429.

    Prefer the endpoint's own Retry-After header, then a delay quoted in the
    error body, then exponential backoff. Capped, because a demo that pauses
    for two minutes is no better than one that fails.
    """
    header = None
    try:
        header = exc.headers.get("Retry-After") or exc.headers.get("retry-after")
    except Exception:                                       # noqa: BLE001
        pass
    if header:
        try:
            return min(float(header) + 0.25, CLU_MAX_BACKOFF_S)
        except ValueError:
            pass
    m = re.search(r"try again in ([0-9.]+)\s*s", detail or "", re.I)
    if m:
        return min(float(m.group(1)) + 0.25, CLU_MAX_BACKOFF_S)
    return min(2.0 ** attempt, CLU_MAX_BACKOFF_S)


class OpenAICompatibleProvider:
    """Groq, OpenRouter, Together, vLLM, Gemini's compatibility endpoint.

    The transcript leaves the machine. That is recorded on every trace, not
    just documented here, because for a banking deployment it is the single
    most consequential property of this provider.
    """
    name = "openai"
    leaves_machine = True

    def __init__(self, model: str | None = None, base: str | None = None):
        self.model = model or CLU_MODEL
        self.base = (base or LLM_API_BASE).rstrip("/")

    def _key(self) -> str | None:
        return os.environ.get(LLM_API_KEY_ENV) or None

    def available(self) -> bool:
        return bool(self._key() and self.base)

    def complete(self, transcript, context):
        import urllib.request
        key = self._key()
        t0 = time.perf_counter()
        if not key:
            return ProviderReply("", self.model, self.name, 0.0, True,
                                 error=f"{LLM_API_KEY_ENV} is not set")
        messages = ([{"role": "system", "content": SYSTEM}] + example_messages()
                    + [{"role": "user", "content": build_user_prompt(transcript, context)}])
        body = json.dumps({
            "model": self.model, "messages": messages,
            "temperature": CLU_TEMPERATURE, "max_tokens": CLU_MAX_TOKENS,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT,
                     "Authorization": f"Bearer {key}"})
        data = None
        last_error = None
        retries = 0
        for attempt in range(CLU_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=CLU_TIMEOUT_S) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode()[:200]
                except Exception:                           # noqa: BLE001
                    pass
                # Never echo the key back, whatever the endpoint said.
                detail = detail.replace(key, "<key>") if key else detail
                last_error = f"HTTP {exc.code}: {detail}"
                if exc.code == 429 and attempt < CLU_MAX_RETRIES:
                    # A 429 is a wait instruction. Honour Retry-After when the
                    # endpoint sends one, otherwise back off exponentially.
                    wait = _retry_after(exc, detail, attempt)
                    time.sleep(wait)
                    retries += 1
                    continue
                break
            except Exception as exc:                        # noqa: BLE001
                last_error = str(exc)
                break

        if data is None:
            return ProviderReply("", self.model, self.name,
                                 (time.perf_counter() - t0) * 1000, True,
                                 error=last_error, meta={"retries": retries})
        usage = data.get("usage") or {}
        return ProviderReply(
            (data.get("choices") or [{}])[0].get("message", {}).get("content", ""),
            data.get("model", self.model), self.name,
            (time.perf_counter() - t0) * 1000, True,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            meta={"endpoint": self.base, "retries": retries})


# ---------------------------------------------------------------- registry

_PROVIDERS = {"null": NullProvider, "mock": MockProvider,
              "ollama": OllamaProvider, "openai": OpenAICompatibleProvider}


def get_provider(name: str | None = None) -> Provider:
    key = (name or CLU_PROVIDER or "null").lower()
    cls = _PROVIDERS.get(key)
    if cls is None:
        raise ValueError(f"unknown CLU provider {key!r}, expected one of {sorted(_PROVIDERS)}")
    return cls()


def provider_names() -> list[str]:
    return sorted(_PROVIDERS)


def prompt_version() -> str:
    return PROMPT_VERSION
