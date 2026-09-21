#!/usr/bin/env python3
"""List the models the configured CLU provider offers.

Groq retires and renames models fairly often, so when a call starts coming
back 404 this is how you find what to put in BFSI_CLU_MODEL.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import CLU_MODEL, CLU_PROVIDER, LLM_API_BASE, LLM_API_KEY_ENV  # noqa: E402


def main() -> int:
    if CLU_PROVIDER == "ollama":
        base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as r:
            for m in json.loads(r.read()).get("models", []):
                print(f"  {m['name']:44s} {m.get('size', 0) / 1e9:.1f} GB")
        return 0

    key = os.environ.get(LLM_API_KEY_ENV)
    if not key:
        print(f"{LLM_API_KEY_ENV} is not set. Put it in .env (gitignored):")
        print(f"  BFSI_CLU_PROVIDER=openai")
        print(f"  {LLM_API_KEY_ENV}=<your key>")
        return 1
    from app.clu.providers import USER_AGENT
    req = urllib.request.Request(
        f"{LLM_API_BASE.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as exc:                                # noqa: BLE001
        print(f"could not list models: {exc}")
        return 1
    models = sorted(m.get("id", "?") for m in data.get("data", []))
    print(f"{len(models)} models at {LLM_API_BASE}. Current BFSI_CLU_MODEL={CLU_MODEL}\n")
    for m in models:
        print(f"  {'* ' if m == CLU_MODEL else '  '}{m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
