#!/usr/bin/env python3
"""Regenerate every figure from code, so the diagrams cannot drift away from
the design the way hand-drawn ones do.

Outputs PNG at 200 DPI and SVG into docs/figures, plus a Mermaid version of
each into docs/figures/mermaid.md for GitHub rendering.

Palette is fixed to match the existing figures in the synopsis:
teal for the voice pipeline, amber for middleware, red for compliance and
escalation.

Run: make diagrams
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "docs" / "figures"

TEAL, TEAL_BG = "#0f766e", "#d8ece9"
AMBER, AMBER_BG = "#b45309", "#fbeed7"
RED, RED_BG = "#b91c1c", "#f9dcdc"
GREY, GREY_BG = "#475569", "#e8ebef"
INK = "#16181d"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})


def box(ax, x, y, w, h, text, edge=TEAL, face=TEAL_BG, fontsize=9, weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.4, edgecolor=edge, facecolor=face))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=INK,
            fontsize=fontsize, fontweight=weight, wrap=True)


def arrow(ax, p0, p1, color=GREY, style="-|>", text=None, rad=0.0, fontsize=8):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=12,
                                 linewidth=1.2, color=color,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + 0.06, text, ha="center",
                va="bottom", fontsize=fontsize, color=color)


def canvas(w, h, title):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 10); ax.set_ylim(0, h / w * 10)
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold", color=INK, pad=10)
    return fig, ax


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  {name}.png and .svg")


# ---------------------------------------------------------------- 1. layers

def fig_layers():
    fig, ax = canvas(10, 7.2, "Figure 1. Four-layer architecture")
    rows = [
        (5.9, "Layer 1  Voice and AI", TEAL, TEAL_BG,
         ["VAD\nsilero", "ASR\nfaster-whisper", "Language ID\nViterbi smoothed",
          "NLU\nMiniLM + logistic", "Dialogue policy\nrisk tiers", "TTS\nPiper"]),
        (4.2, "Layer 2  Integration middleware", AMBER, AMBER_BG,
         ["Core banking\nadapter (SIMULATED)", "Action dispatch\none per intent",
          "RBAC\nsigned JWT", "Session state\ntier ratchet", "Escalation\nrouting"]),
        (2.5, "Layer 3  Compliance", RED, RED_BG,
         ["ComplianceTrace\nthe spine", "PII redaction\nLuhn + Verhoeff",
          "AES-256-GCM\nvault", "Consent and\nretention", "Hash-chained\nledger"]),
        (0.8, "Layer 4  Dashboard", GREY, GREY_BG,
         ["Customer\nconsole", "Trace view", "Ledger verify\nand localise",
          "Escalation\nqueue", "Capability\nlegend"]),
    ]
    for y, label, edge, face, cells in rows:
        ax.add_patch(FancyBboxPatch((0.15, y - 0.25), 9.7, 1.45,
                                    boxstyle="round,pad=0.02,rounding_size=0.06",
                                    linewidth=1.6, edgecolor=edge, facecolor="white"))
        ax.text(0.35, y + 0.98, label, fontsize=10, fontweight="bold", color=edge, va="center")
        w = 9.2 / len(cells)
        for i, cell in enumerate(cells):
            box(ax, 0.4 + i * w, y - 0.1, w - 0.22, 0.85, cell, edge, face, fontsize=7.5)
    for y in (5.65, 3.95, 2.25):
        arrow(ax, (5.0, y), (5.0, y - 0.35), color=GREY)
    ax.text(5.0, 0.35, "every stage writes one record into the trace, and the trace is the audit",
            ha="center", fontsize=8.5, style="italic", color=RED)
    save(fig, "fig1_layers")


# ---------------------------------------------------------------- 2. turn sequence

def fig_turn_sequence():
    fig, ax = canvas(10, 8.4, "Figure 2. One turn from microphone to ledger")
    lanes = [("Caller", 0.9, GREY), ("Voice pipeline", 3.0, TEAL),
             ("Middleware", 5.6, AMBER), ("Compliance", 8.2, RED)]
    top, bottom = 7.6, 0.7
    for name, x, colour in lanes:
        ax.text(x, top + 0.25, name, ha="center", fontsize=9.5, fontweight="bold", color=colour)
        ax.plot([x, x], [bottom, top], color=colour, linewidth=1.0, alpha=0.5, zorder=0)

    steps = [
        (7.35, 0.9, 8.2, "consent captured", RED),
        (7.05, 8.2, 8.2, "ledger record 0", RED),
        (6.7, 0.9, 3.0, "audio or typed text", GREY),
        (6.35, 3.0, 3.0, "VAD, ASR -> transcript, c_asr", TEAL),
        (6.0, 3.0, 3.0, "language ID -> spans, CMI", TEAL),
        (5.65, 3.0, 3.0, "NLU -> intent, c_intent, slots", TEAL),
        (5.3, 3.0, 3.0, "retrieval -> passage, version, or nothing", TEAL),
        (4.95, 3.0, 5.6, "c_final, anomalies", GREY),
        (4.6, 5.6, 5.6, "speaker verify x anti-spoof = s_verify", AMBER),
        (4.25, 5.6, 5.6, "R, tier, gate", AMBER),
        (3.9, 5.6, 5.6, "action, or refuse, or escalate", AMBER),
        (3.55, 5.6, 3.0, "reply text", GREY),
        (3.2, 3.0, 3.0, "TTS in the dominant language", TEAL),
        (2.85, 3.0, 0.9, "spoken reply", GREY),
        (2.4, 5.6, 8.2, "trace, complete", RED),
        (2.05, 8.2, 8.2, "PII redaction, vault write", RED),
        (1.7, 8.2, 8.2, "trace stored, redacted", RED),
        (1.35, 8.2, 8.2, "ledger append, H and HMAC", RED),
    ]
    for y, x0, x1, label, colour in steps:
        if x0 == x1:
            # Width follows the label so the longest lines are not clipped.
            half = max(1.15, 0.035 * len(label) + 0.25)
            ax.add_patch(FancyBboxPatch((x0 - half, y - 0.12), 2 * half, 0.26,
                                        boxstyle="round,pad=0.01,rounding_size=0.04",
                                        linewidth=1.0, edgecolor=colour,
                                        facecolor={TEAL: TEAL_BG, AMBER: AMBER_BG,
                                                   RED: RED_BG, GREY: GREY_BG}[colour]))
            ax.text(x0, y, label, ha="center", va="center", fontsize=6.8, color=INK)
        else:
            arrow(ax, (x0, y), (x1, y), color=colour)
            ax.text((x0 + x1) / 2, y + 0.07, label, ha="center", va="bottom",
                    fontsize=7.2, color=colour)
    ax.text(5.0, 0.85, "raw audio is dropped as soon as the transcript exists, and nothing "
                       "reaches disk before redaction",
            ha="center", fontsize=8, style="italic", color=RED)
    save(fig, "fig2_turn_sequence")


# ---------------------------------------------------------------- 3. risk tiers

def fig_risk_tiers():
    from app.config import (MIN_TIER_BY_INTENT, RISK_WEIGHTS, TIER_CUTPOINTS,
                            TIER_TAU)
    fig, ax = canvas(10, 8.0, "Figure 3. Risk tier decision flow")
    t1, t2, t3 = TIER_CUTPOINTS
    w = RISK_WEIGHTS

    box(ax, 2.6, 7.0, 4.8, 0.72,
        f"R = {w['sens']}*sens(intent) + {w['amount']}*norm(amount)\n"
        f"  + {w['verify']}*(1 - s_verify) + {w['history']}*dev(history)",
        AMBER, AMBER_BG, fontsize=8.5, weight="bold")

    box(ax, 0.3, 5.9, 3.0, 0.62,
        "hard override\nfraud_report, dispute_txn, agent_request", RED, RED_BG, 7.5)
    box(ax, 3.5, 5.9, 3.0, 0.62,
        "intent floor\nread 1, mutate 2, override 3", RED, RED_BG, 7.5)
    box(ax, 6.7, 5.9, 3.0, 0.62,
        "session ratchet\ntier never decreases", RED, RED_BG, 7.5)
    for x in (1.8, 5.0, 8.2):
        arrow(ax, (x, 5.85), (5.0, 5.35), color=RED, rad=0.05)
    box(ax, 2.6, 4.75, 4.8, 0.55,
        "applied tier = max(scored, intent floor, session floor)", RED, "white", 8.5, "bold")

    tiers = [
        (3.45, "Tier 0   R < %.2f" % t1, "public information, no authentication",
         f"tau = {TIER_TAU[0]}", TEAL, TEAL_BG),
        (2.6, "Tier 1   %.2f <= R < %.2f" % (t1, t2),
         "account specific, passive speaker verification", f"tau = {TIER_TAU[1]}", TEAL, TEAL_BG),
        (1.75, "Tier 2   %.2f <= R < %.2f" % (t2, t3),
         "transactional, verification + OTP + spoken read-back",
         f"tau = {TIER_TAU[2]}", AMBER, AMBER_BG),
        (0.9, "Tier 3   R >= %.2f, or override" % t3,
         "mandatory human handover with the context packet",
         f"tau = {TIER_TAU[3]}, unreachable", RED, RED_BG),
    ]
    for y, title, desc, tau, edge, face in tiers:
        ax.add_patch(FancyBboxPatch((1.1, y - 0.03), 7.8, 0.66,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    linewidth=1.4, edgecolor=edge, facecolor=face))
        ax.text(1.35, y + 0.42, title, fontsize=9, fontweight="bold", color=edge, va="center")
        ax.text(1.35, y + 0.17, desc, fontsize=8, color=INK, va="center")
        ax.text(8.65, y + 0.3, tau, fontsize=7.5, color=edge, ha="right", va="center")
    arrow(ax, (5.0, 4.7), (5.0, 4.15), color=RED)
    ax.text(5.0, 0.45,
            "automate only if R < cut-point AND c_final >= tau AND verification passed "
            "AND grounding cleared",
            ha="center", fontsize=8, style="italic", color=INK)
    save(fig, "fig3_risk_tiers")


# ---------------------------------------------------------------- 4. ledger

def fig_ledger():
    from app.config import LEDGER_CHECKPOINT_INTERVAL as K
    fig, ax = canvas(10, 5.6, "Figure 4. Hash chain, checkpoints and tamper localisation")
    y = 3.7
    labels = ["M0\nconsent", "M1\nturn", "M2\nturn", "...", "Mi\nturn", "...", "Mn\npurge"]
    for i, label in enumerate(labels):
        x = 0.35 + i * 1.35
        face = RED_BG if label.startswith("Mi") else TEAL_BG
        edge = RED if label.startswith("Mi") else TEAL
        box(ax, x, y, 1.05, 0.7, label, edge, face, 8)
        if i:
            arrow(ax, (x - 0.3, y + 0.35), (x - 0.02, y + 0.35), color=GREY)
    ax.text(5.0, y + 1.15,
            "H(i) = SHA-256( H(i-1) || canonical_json(M_i) || t_i )      "
            "sig(i) = HMAC-SHA-256( key, H(i) )",
            ha="center", fontsize=9, fontweight="bold", color=INK)
    ax.text(5.0, y - 0.35, f"checkpoint anchor written every k = {K} records",
            ha="center", fontsize=8, color=AMBER)
    for i in (1, 4):
        x = 0.35 + i * 1.35 + 0.52
        ax.plot([x, x], [y - 0.05, y - 0.25], color=AMBER, linewidth=1.2)
        ax.plot(x, y - 0.3, marker="v", color=AMBER, markersize=5)

    box(ax, 0.35, 1.6, 4.3, 1.4,
        "Tamper detected by one of three checks\n\n"
        "link      prev_hash does not match the predecessor\n"
        "binding   hash does not match this payload\n"
        "sig       HMAC does not match, no key to forge it",
        RED, "white", 8)
    box(ax, 5.15, 1.6, 4.5, 1.4,
        "Cost\n\n"
        "append            O(1)\n"
        "full verify       O(n)\n"
        "locate, rewritten chain   O(log(n/k)) probes of O(k)\n"
        "locate, single row edit   walk the n/k anchors",
        AMBER, "white", 8)
    ax.text(5.0, 1.15, "beat 10: one SQL UPDATE on a payload, no hash recomputed, "
                       "chain goes red and names the record",
            ha="center", fontsize=8, style="italic", color=RED)
    save(fig, "fig4_ledger")


# ---------------------------------------------------------------- 5. data lifecycle

def fig_lifecycle():
    from app.config import CONSENT_RETENTION_DAYS
    fig, ax = canvas(10, 6.0, "Figure 5. Data lifecycle from consent to purge")
    steps = [
        ("Consent\npurpose and retention\nstated and spoken", RED),
        ("Capture\naudio in memory only", TEAL),
        ("Transcribe\naudio dropped\nimmediately after", TEAL),
        ("Process\nlangid, NLU, retrieval,\nrisk, decision", TEAL),
        ("Redact\ntokens out,\nvalues into the vault", RED),
        ("Persist\nredacted trace,\nencrypted vault", RED),
        ("Append\nhash-chained\nledger record", RED),
    ]
    w = 9.4 / len(steps)
    for i, (label, colour) in enumerate(steps):
        face = TEAL_BG if colour == TEAL else RED_BG
        box(ax, 0.3 + i * w, 3.6, w - 0.18, 1.2, label, colour, face, 7.5)
        if i:
            arrow(ax, (0.3 + i * w - 0.16, 4.2), (0.3 + i * w - 0.02, 4.2), color=GREY)

    box(ax, 0.3, 1.9, 4.4, 1.0,
        f"Retention\nkept for {CONSENT_RETENTION_DAYS} days, then due for deletion\n"
        "purpose limited to handling the request",
        AMBER, AMBER_BG, 8)
    box(ax, 5.3, 1.9, 4.4, 1.0,
        "Withdrawal\nvault rows and transcripts deleted\n"
        "purge record appended, ledger still verifies",
        RED, RED_BG, 8)
    arrow(ax, (2.5, 3.55), (2.5, 2.95), color=AMBER)
    arrow(ax, (7.5, 3.55), (7.5, 2.95), color=RED)
    ax.text(5.0, 1.4,
            "the ledger holds hashes and tokens, never identifiers, so it survives an "
            "erasure and proves the erasure happened",
            ha="center", fontsize=8, style="italic", color=RED)
    save(fig, "fig5_lifecycle")


# ---------------------------------------------------------------- mermaid

MERMAID = """# Figures, Mermaid source

These render inline on GitHub. The publication-quality PNG and SVG versions in
this directory are generated by `scripts/diagrams/generate.py` (`make diagrams`).

## Figure 1. Four-layer architecture

```mermaid
flowchart TB
  subgraph L1["Layer 1  Voice and AI"]
    VAD[VAD silero] --> ASR[ASR faster-whisper]
    ASR --> LID[Language ID, Viterbi smoothed]
    LID --> NLU[NLU MiniLM + logistic head]
    NLU --> RET[Retrieval, versioned policy KB]
    RET --> POL[Dialogue policy, risk tiers]
    POL --> TTS[TTS Piper]
  end
  subgraph L2["Layer 2  Integration middleware"]
    CORE[Core banking adapter SIMULATED]
    ACT[Action dispatch, one per intent]
    RBAC[RBAC signed JWT]
    SESS[Session state, tier ratchet]
    ESC[Escalation routing]
  end
  subgraph L3["Layer 3  Compliance"]
    TRACE[ComplianceTrace]
    PII[PII redaction, Luhn + Verhoeff]
    VAULT[AES-256-GCM vault]
    CONS[Consent and retention]
    LED[Hash-chained ledger]
  end
  subgraph L4["Layer 4  Dashboard"]
    CUST[Customer console]
    TV[Trace view]
    LV[Ledger verify and localise]
    Q[Escalation queue]
    CAP[Capability legend]
  end
  L1 --> L2 --> L3 --> L4
```

## Figure 2. One turn

```mermaid
sequenceDiagram
  participant C as Caller
  participant V as Voice pipeline
  participant M as Middleware
  participant K as Compliance
  C->>K: consent, purpose and retention
  K-->>K: ledger record 0
  C->>V: audio, or typed text
  V-->>V: VAD, ASR, transcript and c_asr
  V-->>V: language ID, spans and CMI
  V-->>V: NLU, intent and slots
  V-->>V: retrieval, passage with version, or nothing
  V->>M: c_final, anomalies
  M-->>M: speaker verify x anti-spoof = s_verify
  M-->>M: R, tier, gate
  M-->>M: action, or refuse, or escalate
  M->>V: reply text
  V->>C: spoken reply
  M->>K: completed trace
  K-->>K: PII redaction, vault write
  K-->>K: store redacted trace
  K-->>K: append to the hash chain
```

## Figure 3. Risk tiers

```mermaid
flowchart TB
  R["R = 0.40 sens + 0.25 norm(amount) + 0.25 (1 - s_verify) + 0.10 dev(history)"]
  R --> S{scored tier from cut-points 0.25, 0.50, 0.75}
  HO[hard override: fraud_report, dispute_txn, agent_request] --> MAX
  IF[intent floor: read 1, mutate 2] --> MAX
  SR[session ratchet: never decreases] --> MAX
  S --> MAX{"applied tier = max of the three"}
  MAX --> T0[Tier 0 public information, tau 0.50]
  MAX --> T1[Tier 1 passive speaker verification, tau 0.62]
  MAX --> T2[Tier 2 verification + OTP + read-back, tau 0.75]
  MAX --> T3[Tier 3 human handover, tau 1.01 unreachable]
```

## Figure 4. Ledger

```mermaid
flowchart LR
  M0[M0 consent] --> M1[M1 turn] --> M2[M2 turn] --> Mi[Mi turn] --> Mn[Mn purge]
  CP1[checkpoint anchor] -.-> M1
  CP2[checkpoint anchor] -.-> Mi
  Mi -.->|payload edited, no hash recomputed| BREAK[binding check fails, record named]
```

## Figure 5. Data lifecycle

```mermaid
flowchart LR
  A[Consent] --> B[Capture, memory only] --> C[Transcribe, audio dropped]
  C --> D[Process] --> E[Redact, vault write] --> F[Persist redacted trace]
  F --> G[Append ledger record]
  F --> H[Retention window]
  H --> I[Withdrawal: purge vault and transcripts]
  I --> J[Purge record appended, ledger still verifies]
```
"""


def main() -> int:
    print("generating figures into docs/figures")
    fig_layers()
    fig_turn_sequence()
    fig_risk_tiers()
    fig_ledger()
    fig_lifecycle()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mermaid.md").write_text(MERMAID)
    print("  mermaid.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
