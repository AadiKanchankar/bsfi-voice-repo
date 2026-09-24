# CLAUDE.md

Compliance-aware multilingual voice assistant for BFSI. B.Tech final year
project, Group GC19, Department of Computer Engineering, PCCOE Pune. Paper
target: CCIT 2026.

**Read `graphify-out/GRAPH_REPORT.md` before searching raw files.** The graph
knows the structure. This file and `docs/DECISIONS.md` know the judgement.

## Hard rules, no exceptions

1. **No em dashes** in any user-facing string, spoken text, comment or
   document. `make check-honesty` enforces it.
2. **The honesty registry is the source of truth.** Every component declares
   itself `REAL`, `BASELINE` or `SIMULATED` in `backend/app/capabilities.py`.
   Anything that sends data off the machine also carries that fact, and the
   dashboard renders it. Never let the demo imply a capability it lacks.
3. **Never automate a tier 3 resolution.** Fraud reports, disputes, agent
   requests and investment advice are mandatory human handover. `tau[3] =
   1.01` makes tier 3 unreachable by construction, not by policy. Reducing
   harm (a temporary freeze) is not the same as resolving; see D-entries in
   `docs/DECISIONS.md`.
4. **No real personal data in the repository, ever.** Customers, accounts,
   cards, transactions and enrolled voices are synthetic and seeded from a
   fixed seed. A presenter's own name goes in `BFSI_PRESENTER_NAME` in
   `.env`, never in a committed file.
5. **No metric that was not measured.** Nothing goes in `docs/RESULTS.md`
   that `make eval` did not compute. Literature figures are labelled as
   literature.
6. **The deterministic layer is authoritative.** The language model layer
   (CLU) may propose an interpretation and may raise the assessed risk of a
   turn. It may never lower it, reach an action, or decide anything.

## Running it

```
make setup      # venv, Python deps, npm install. Needs network, once.
make models     # pre-download every model. Needs network, once.
make seed       # synthetic data, intent head, KB index, enrolled voices
make demo       # backend on :8000, frontend on :5173
```

Customer console at `http://127.0.0.1:5173/`, compliance dashboard at
`/compliance`. Cold start is about 6 seconds.

```
make test           # full pytest suite
make eval           # regenerates docs/RESULTS.md from scratch
make clu-eval       # baseline against baseline+CLU, writes docs/CLU_RESULTS.md
make clu-check      # is a CLU provider configured and reachable
make clu-models     # what the provider actually serves today
make tamper         # corrupt one ledger record, for demo beat 10
make restore        # undo it
make verify         # verify the ledger from the command line
make diagrams       # regenerate the figures
make check-honesty  # em dash scan
```

## Where each subsystem lives

| Concern | Path |
| --- | --- |
| The trace threaded through every stage | `backend/app/trace.py` |
| Schema, migrations, connections | `backend/app/models.py`, `backend/alembic/`, `backend/app/db.py` |
| Customers, enrolments, recordings | `backend/app/banking/registry.py`, `backend/app/security/recordings.py` |
| Every threshold and weight | `backend/app/config.py` |
| What is real and what is not | `backend/app/capabilities.py` |
| Turn orchestration | `backend/app/turn.py` |
| Speech in and out | `backend/app/pipeline/{vad,asr,tts,prosody,speech_text}.py` |
| Cloud speech providers and fallback | `backend/app/pipeline/providers.py` |
| Fillers, variation, the honesty answer | `backend/app/pipeline/voice_style.py` |
| Call state machine, barge-in | `backend/app/call.py` |
| Compliance lookup and access logging | `backend/app/compliance.py` |
| Code-switch language ID | `backend/app/pipeline/langid.py` |
| Intent, slots, retrieval | `backend/app/pipeline/{nlu,slots,retrieval}.py` |
| Risk, fusion, the gate | `backend/app/pipeline/dialogue.py` |
| Contextual language layer | `backend/app/clu/` |
| Ledger, PII, speaker, RBAC, crypto | `backend/app/security/` |
| Mock core banking and one action per intent | `backend/app/banking/` |
| Metrics and harnesses | `backend/app/eval/` |
| UI | `frontend/src/routes/`, `frontend/src/components/` |

## Conventions

- **Config, not constants.** Any number that influences a decision lives in
  `config.py` and nowhere else.
- **Every stage writes to the trace.** If a value influenced an outcome, a
  reviewer must be able to recompute that outcome from the trace alone.
  `tests/test_risk.py::test_recompute_from_components_matches_stored_score`
  is the machine-checked version of that claim.
- **Tests assert behaviour, not implementation.** Where a test pins a
  deliberate limitation, it says so in the docstring.
- **Comments explain why, never what.** Several explain a bug that was
  actually hit; leave those alone, they are load-bearing.
- **Deliberate shortcuts get a `ponytail:` comment** naming the ceiling and
  the upgrade path.
- **A cloud dependency on a free tier does not fail, it waits.** Anything
  that measures a system containing one decides explicitly whether it is
  measuring the system or the queue. This has bitten twice: `docs/DECISIONS.md`
  D30.

## Before you change anything

- Behaviour change? Add an entry to `docs/DECISIONS.md`.
- Touching the risk formula, tier cut-points, retention window, consent
  wording, or weakening a test? Ask first. Those are listed as sign-off
  items in `TASKS/CHANGE_REQUEST_02.md`.
- Claiming an improvement? Report a before number and an after number.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
