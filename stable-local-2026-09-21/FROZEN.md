# Frozen snapshot, 2026-09-21

This is the working local-only system as it stood before the Contextual
Language Understanding (CLU) experiment began. It is the fallback: if the
experiment goes wrong, this is what gets demonstrated to the review panel.

**Do not edit anything in this directory.** Build in the parent directory.

## What it is

The compliance-aware voice assistant with deterministic NLU: MiniLM
embeddings plus a logistic-regression head, rule-based slots, no network
calls at inference time. 218 tests passing, `make eval` reproducing every
number in `docs/RESULTS.md`.

## Running it

`.venv` and `models` are symlinks into the parent project, so this snapshot
stays at 12 MB instead of duplicating 3 GB. It is runnable as long as the
parent still has them:

```
cd stable-local-2026-09-21
BFSI_RUNTIME_DIR=$PWD/runtime PYTHONPATH=backend ../.venv/bin/python -m pytest backend/tests -q
BFSI_RUNTIME_DIR=$PWD/runtime PYTHONPATH=backend ../.venv/bin/python scripts/seed_data.py
BFSI_RUNTIME_DIR=$PWD/runtime PYTHONPATH=backend ../.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8001
```

`BFSI_RUNTIME_DIR` is set so the snapshot keeps its own database, trained
head and calibration, rather than sharing the parent's and drifting with it.

If the parent is ever deleted, recreate the two dependencies with
`make setup && make models` from inside this directory after replacing the
symlinks with real directories.

## Known state at freeze

- Intent head: 5-fold CV accuracy 0.836 on 397 seeded utterances
- Dominant-language accuracy 0.74; romanised Hindi and Marathi outside the
  seeded lexicon fall through to English
- Retrieval floor delta 0.50, precision 0.94, recall 0.89
- Marathi answerable queries: 0 of 2 clear the floor
- English WER 0.094, English entity error rate 0.158

These are the numbers the experiment has to beat.
