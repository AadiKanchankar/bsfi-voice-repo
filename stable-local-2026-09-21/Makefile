# Compliance-Aware Multilingual Voice Assistant for BFSI
# Group GC19, Department of Computer Engineering, PCCOE Pune
#
# Order for a cold machine:  make setup && make models && make seed && make demo

SHELL := /bin/bash
PY := .venv/bin/python
PIP := .venv/bin/pip
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

# The Hugging Face Xet transfer backend stalls on some networks and leaves zero
# byte downloads behind. Plain HTTPS is reliable, which is what matters here.
export HF_HUB_DISABLE_XET := 1
export PYTHONPATH := $(CURDIR)/backend
export TOKENIZERS_PARALLELISM := false

.PHONY: help setup models seed demo backend frontend test test-fast eval eval-audio \
        diagrams tamper restore verify clean distclean check-honesty

help:
	@echo "setup        create the venv and install Python and Node dependencies"
	@echo "models       pre-download every model (needs network, run once)"
	@echo "seed         generate synthetic data, train the intent head, build the KB index"
	@echo "demo         run backend and frontend together"
	@echo "test         full pytest suite"
	@echo "test-fast    everything except the tests that load speech models"
	@echo "eval-audio   render the evaluation set to audio with Piper"
	@echo "eval         run the metrics harness and regenerate docs/RESULTS.md"
	@echo "diagrams     regenerate the figures in docs/figures"
	@echo "tamper       corrupt one ledger record for demo beat 10"
	@echo "restore      undo the tamper"
	@echo "verify       verify the ledger from the command line"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt
	cd frontend && npm install

models:
	$(PY) scripts/download_models.py

seed:
	$(PY) scripts/seed_data.py

demo:
	@echo "backend on http://127.0.0.1:$(BACKEND_PORT)  frontend on http://127.0.0.1:$(FRONTEND_PORT)"
	@trap 'kill 0' EXIT INT TERM; \
	 $(PY) -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $(BACKEND_PORT) & \
	 (cd frontend && npm run dev -- --port $(FRONTEND_PORT) --host 127.0.0.1) & \
	 wait

backend:
	$(PY) -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $(BACKEND_PORT) --reload

frontend:
	cd frontend && npm run dev -- --port $(FRONTEND_PORT)

test:
	$(PY) -m pytest backend/tests -q

test-fast:
	$(PY) -m pytest backend/tests -q -m "not slow"

eval-audio:
	$(PY) scripts/make_eval_set.py

eval:
	$(PY) -c "from app.eval.harness import run_all; r = run_all(); print('wrote docs/RESULTS.md')"

diagrams:
	$(PY) scripts/diagrams/generate.py

tamper:
	$(PY) scripts/tamper_demo.py

restore:
	$(PY) scripts/tamper_demo.py --restore

verify:
	$(PY) -c "from app import db; from app.security import ledger; import json; print(json.dumps(ledger.verify(db.init_db()), indent=2))"

check-honesty:
	@echo "checking for em dashes in user-facing text and docs"
	@! grep -rn $$'—' --include='*.py' --include='*.md' --include='*.tsx' --include='*.ts' \
	   backend frontend/src docs data scripts 2>/dev/null || (echo "em dash found, replace it" && false)
	@echo "ok"

clean:
	rm -rf runtime .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

distclean: clean
	rm -rf .venv models frontend/node_modules data/eval/audio data/seed/voices data/seed/spoofs
