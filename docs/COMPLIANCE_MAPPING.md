# Compliance control mapping

Each implemented control mapped to the regulatory obligation it serves, with
the file that implements it and the test that proves it does.

> **Read this caveat before citing this table in the paper.** The obligations
> below are quoted as the project synopsis summarises them, not transcribed
> from the source documents. Recommendation numbers from the RBI FREE-AI
> committee report are deliberately **not** cited here, because getting a
> recommendation number wrong in a compliance table is worse than leaving it
> out. Before this table goes into a submission, somebody on the team must
> open the FREE-AI report (August 2025) and the DPDP Rules (notified 13
> November 2025) and fill in the exact clause references in the empty column.
> The engineering side of each row is accurate and testable today.

## RBI FREE-AI committee report, August 2025

The synopsis summarises the committee as setting out seven guiding principles
and 26 recommendations, and names four obligations specifically. Those four
are the rows below.

| Obligation (as summarised in the synopsis) | What this system does | Where | Test | Clause ref |
| --- | --- | --- | --- | --- |
| Board-approved AI policy | Not an engineering control. What the system provides is the artefact such a policy would govern: a single declared inventory of every AI component with its status and its limitations, which is what a board would be asked to approve. | `backend/app/capabilities.py`, `GET /capabilities` | `test_api.py::test_capabilities_is_open_and_declares_everything` | *to fill* |
| Explainability by design | Every stage of every turn appends a record carrying its inputs digest, outputs, confidence, model id, duration and capability status. The risk score is stored with every term of the formula, and a reviewer can recompute the decision from the stored components alone. The dashboard renders the whole chain of reasoning for one turn. | `backend/app/trace.py`, `backend/app/turn.py`, `frontend/src/components/TraceView.tsx` | `test_risk.py::test_recompute_from_components_matches_stored_score` | *to fill* |
| Continuous post-deployment monitoring | Per-stage latency percentiles and decision counters are read off the stored traces and exposed on the dashboard. The evaluation harness regenerates every accuracy number from scratch and rewrites the measured operating points (`delta`, `theta`) that the running system then uses. | `GET /metrics`, `backend/app/eval/harness.py`, `runtime/calibration.json` | `test_api.py::test_metrics_shape` | *to fill* |
| Clear accountability across the model lifecycle | Every trace stage names the exact model that produced it, including size and quantisation. Every ledger record is signed. Handovers record the claiming agent. Enrolment records whether the voice was synthetic or live. | `StageRecord.model_id`, `backend/app/security/ledger.py`, `POST /agent/handover/{trace_id}` | `test_ledger.py`, `test_scenarios.py::test_beat_7_tier3_hard_override_and_handover` | *to fill* |
| Human oversight of consequential decisions (the committee's stated rationale for human-in-the-loop) | Four risk tiers with friction proportional to consequence. Tier 3 is mandatory human handover and is unreachable by automation by construction, since `tau[3] = 1.01` exceeds the maximum possible confidence. Fraud reports, disputes and agent requests bypass the score entirely. | `backend/app/pipeline/dialogue.py` | `test_risk.py::test_hard_override_beats_any_score`, `::test_tier3_tau_is_unreachable` | *to fill* |

## DPDP Act 2023 and DPDP Rules, notified 13 November 2025

| Obligation (as summarised in the synopsis) | What this system does | Where | Test | Clause ref |
| --- | --- | --- | --- | --- |
| Itemised consent notice | The session cannot open without consent. The notice states the purpose and the retention period in the caller's language before any audio is processed, and it is spoken, not buried in a checkbox. The consent record, including purpose and retention, is the first entry in the audit ledger. | `turn.create_session`, `turn.consent_notice` | `test_scenarios.py::test_beat_1_consent_is_the_first_ledger_entry`, `test_api.py::test_consent_required_to_open_a_session` | *to fill* |
| Purpose limitation | The consent record names one purpose: handling the caller's banking request. Every action the system can take is one function per intent, and no path exists from a turn to any use of the data other than answering it and auditing it. | `backend/app/config.py CONSENT_PURPOSE`, `backend/app/banking/actions.py` | `test_scenarios.py` beats 2 to 7 | *to fill* |
| Purpose-limited retention | The retention period is recorded in the consent record and in the ledger at the moment consent is given, so the clock on every session is auditable. | `CONSENT_RETENTION_DAYS`, `consents` table | `test_scenarios.py::test_beat_1_consent_is_the_first_ledger_entry` | *to fill* |
| Right to erasure, and propagation to downstream stores | Consent withdrawal deletes the PII vault rows and the transcripts for that session, and appends a purge record to the ledger. The session is then closed to further turns. The ledger itself survives, and deliberately: it holds hashes and tokens, never identifiers, and deleting it would destroy the evidence that the erasure happened. | `turn.withdraw_consent`, `crypto.purge_session` | `test_scenarios.py::test_consent_withdrawal_purges_and_records_the_purge` | *to fill* |
| Data minimisation at write time | Identifiers are detected and tokenised before anything reaches disk. Raw audio is held in memory only for as long as transcription needs it. Each trace stage stores the SHA-256 digest of its input, never the input. | `backend/app/security/pii.py`, `trace._input_digest`, `turn.finalise` | `test_scenarios.py::test_beat_8_pii_is_tokenised_and_no_raw_audio_on_disk` | *to fill* |
| Security safeguards for personal data | Raw identifiers are held in a per-session AES-256-GCM vault, in a separate table from the transcripts, with the session id as additional authenticated data so a row moved between sessions fails to decrypt. | `backend/app/security/crypto.py` | `test_security.py::test_aad_binds_ciphertext_to_its_session`, `::test_vault_holds_ciphertext_only` | *to fill* |
| Access control over personal data | Four roles with an explicit permission matrix. A customer token cannot read the compliance export. Every endpoint except the capability registry and the health check requires a signed token. | `backend/app/security/rbac.py` | `test_rbac.py`, `test_api.py::test_customer_cannot_export_the_ledger` | *to fill* |
| Breach reporting within 72 hours | **Not implemented.** The detection half exists: `POST /ledger/verify` localises a tamper to the exact record, which is what a breach report would have to describe. There is no notification pipeline and no 72 hour timer. Listed here because an incomplete control that is declared is worth more than one that is quietly skipped. | `POST /ledger/verify` | `test_ledger.py`, `test_scenarios.py::test_beat_10_...` | *to fill* |
| Enhanced duties for significant data fiduciaries | **Not implemented.** Out of scope for a demo. Would require a documented DPIA, an appointed data protection officer and independent audit, none of which is an engineering artefact. | not applicable | none | *to fill* |

## What is deliberately not claimed

- No control here has been assessed by a compliance function. The claim is
  that each control is implemented and tested, not that it satisfies a
  regulator.
- The two rows marked **Not implemented** are stated rather than omitted. A
  mapping table that only lists the rows that pass is a marketing document.
- The paper's Section IV currently describes a blockchain-based audit trail
  inherited from the base system. This implementation uses a hash chain with
  HMAC signatures instead, as the synopsis argues for. The paper should be
  updated before submission so the text and the artefact agree.
