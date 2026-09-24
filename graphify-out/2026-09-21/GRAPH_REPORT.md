# Graph Report - Projectdemo  (2026-09-21)

## Corpus Check
- 116 files · ~106,927 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 7, .ini 2, .example 1)

## Summary
- 1713 nodes · 3782 edges · 94 communities (92 shown, 2 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 213 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `abd3398d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ledger.py
- test_rbac.py
- seed_data.py
- audio_io.py
- tts.py
- antispoof.py
- MockCore
- ComplianceTrace
- turn.py
- pii.py
- Substitution rule
- test_scenarios.py
- langid.py
- test_tts_language.py
- config.py
- Contextual language understanding layer
- test_investment.py
- test_api.py
- Compliance-Aware Multilingual Voice Assistant for BFSI
- test_clu.py
- nlu.py
- merge_with_baseline
- A7 PII redaction before persistence
- A5 risk scoring
- ProviderReply
- extract
- Intent: product_info
- CLUResult
- Ten-beat demo script
- api.ts
- compilerOptions
- dialogue.py
- Measured results
- Seeded Intent Bank (A3 intent head)
- harness.py
- POL-FEE-007 Schedule of Fees and Charges v4.1
- clu_harness.py
- test_metrics.py
- retrieval.py
- POL-HL-001 Home Loan Interest Rates v1.1 (current)
- Automated Investment Advice Refusal
- Decision log
- generate.py
- Hard tier 3 override
- TraceView.tsx
- assign_tier
- package.json
- MockProvider
- main.tsx
- speaker.py
- gate
- test_risk.py
- ratchet_applies
- test_call_state.py
- POL-GRV-005 Grievance Redressal and Escalation v2.0
- providers.py
- models.py
- POL-BRN-006 Branch Network and IFSC Codes v1.2
- needs_grounding
- POL-KYC-004 Know Your Customer Requirements v3.0
- devDependencies
- test_compliance_lookup.py
- require
- ratchet_should_raise
- test_recompute_from_components_matches_stored_score
- dependencies
- pytest
- cryptography
- main.py
- crypto.py
- create_session
- run_turn
- test_persistence.py
- db.py
- _act
- post
- recordings.py
- status_of
- metrics.py
- prosody.py
- save_enrollment
- e2e/conftest.py
- pipeline/__init__.py
- capabilities.py
- OpenAICompatibleProvider
- classify
- align
- app/__init__.py
- assert_devanagari
- text_turn
- vad.py
- Provider
- latency_from_traces
- _sqlite_path_from_url

## God Nodes (most connected - your core abstractions)
1. `MockCore` - 47 edges
2. `run_turn()` - 46 edges
3. `utcnow()` - 44 edges
4. `ComplianceTrace` - 37 edges
5. `require()` - 36 edges
6. `conn()` - 35 edges
7. `append()` - 32 edges
8. `Decision log` - 28 edges
9. `create_session()` - 25 edges
10. `store()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `D11. Not every tier 3 is a risk signal` --references--> `investment_advice()`  [INFERRED]
  docs/DECISIONS.md → backend/app/banking/actions.py
- `D14. The similarity floor was calibrated against the wrong negative class` --references--> `out_of_scope()`  [INFERRED]
  docs/DECISIONS.md → backend/app/banking/actions.py
- `D24. BFSI_DB_URL pointed the migrations and the reads at different files` --references--> `db_url()`  [INFERRED]
  docs/DECISIONS.md → backend/app/config.py
- `D7. Two different things were both called EER` --references--> `entity_error_rate()`  [INFERRED]
  docs/DECISIONS.md → backend/app/eval/metrics.py
- `D21. Call audio is recorded and kept, reversing the drop-after-transcription rule` --references--> `access_log()`  [INFERRED]
  docs/DECISIONS.md → backend/app/main.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The four architectural layers** — docs_architecture_voice_and_ai_layer, docs_architecture_integration_middleware_layer, docs_architecture_compliance_layer, docs_architecture_dashboard_layer, docs_architecture_four_layer_architecture [EXTRACTED 1.00]
- **Home Loan Rate Policy Version Chain (POL-HL-001)** — data_policy_kb_home_loan_rates_v1_pol_hl_001, data_policy_kb_home_loan_rates_v2_pol_hl_001, data_policy_kb_home_loan_rates_v1_interest_rate_slabs, data_policy_kb_home_loan_rates_v2_interest_rate_slabs, data_policy_kb_home_loan_rates_v1_processing_fee, data_policy_kb_home_loan_rates_v2_processing_fee, data_policy_kb_loan_eligibility_home_loan_eligibility [EXTRACTED 1.00]
- **Enforced risk-tier safety properties** — docs_algorithms_hard_tier_override, docs_algorithms_session_tier_ratchet, docs_algorithms_ratchet_guards, docs_algorithms_min_tier_by_intent, docs_algorithms_four_tier_ladder, docs_algorithms_automation_gate [EXTRACTED 1.00]
- **Stages of one audited turn** — docs_algorithms_code_switch_language_identification, docs_algorithms_intent_classification, docs_algorithms_retrieval_grounding, docs_algorithms_confidence_fusion, docs_algorithms_speaker_verification, docs_algorithms_risk_scoring, docs_algorithms_automation_gate, docs_algorithms_pii_redaction, docs_algorithms_tamper_evident_ledger [EXTRACTED 1.00]
- **Compromised Card Response Flow** — data_seed_intent_bank_block_card, data_seed_intent_bank_fraud_report, data_policy_kb_card_blocking_card_block, data_policy_kb_card_blocking_unauthorised_transaction_liability, data_policy_kb_card_blocking_replacement_card, data_policy_kb_fraud_reporting_shadow_credit, data_policy_kb_fraud_reporting_cybercrime_portal_reference [INFERRED 0.85]
- **Refusal and Human Handoff Path** — data_seed_intent_bank_out_of_scope, data_seed_intent_bank_investment_advice, data_seed_intent_bank_agent_request, data_policy_kb_investment_advice_policy_investment_advice_refusal, data_policy_kb_fraud_reporting_fraud_report_handling, data_policy_kb_investment_advice_policy_suitability_and_risk_profiling [INFERRED 0.85]

## Communities (94 total, 2 thin omitted)

### Community 0 - "ledger.py"
Cohesion: 0.09
Nodes (53): append(), _check_record(), _checkpoints(), compute_hash(), export(), head(), _key(), Any (+45 more)

### Community 1 - "test_rbac.py"
Cohesion: 0.13
Nodes (21): allowed(), current_principal(), decode_token(), issue_token(), Demo-scale RBAC: signed JWT, four hardcoded roles. The production design in the…, _dep(), parametrize, Section 8. The role matrix, walked cell by cell. The cell that matters most: a… (+13 more)

### Community 2 - "seed_data.py"
Cohesion: 0.19
Nodes (18): mask_mobile(), Store and show the last four only. A registered mobile is an identifier; the…, _channel(), luhn_card(), luhn_card_ending(), main(), ndarray, Random (+10 more)

### Community 3 - "audio_io.py"
Cohesion: 0.11
Nodes (27): decode(), _decode_container(), duration_s(), _is_container(), ndarray, Audio helpers shared by VAD, ASR, speaker verification and anti-spoofing.…, Bytes to float32 mono at SAMPLE_RATE. Handles WAV directly, anything else…, Decode a compressed container with PyAV, resampling to mono 16 kHz. PyAV ships… (+19 more)

### Community 4 - "tts.py"
Cohesion: 0.19
Nodes (21): engine(), _kokoro(), kokoro_voice(), _lang(), model_id(), _piper(), piper_voice(), ndarray (+13 more)

### Community 5 - "antispoof.py"
Cohesion: 0.15
Nodes (18): run_biometrics(), AntiSpoofScorer, _deltas(), lfcc(), LfccGmmScorer, _linear_filterbank(), model_id(), ndarray (+10 more)

### Community 6 - "MockCore"
Cohesion: 0.07
Nodes (14): MockCore, Connection, Current value, cost and unrealised gain. Facts only: nothing here is a view on…, Match on the words of the question, not the whole sentence. A LIKE pattern…, core(), fixture, The mock core banking layer. SIMULATED, but its lookups still have to work., A LIKE pattern built from the entire utterance matches nothing, which silently… (+6 more)

### Community 7 - "ComplianceTrace"
Cohesion: 0.25
Nodes (19): add_payee(), _amt(), answer_from_policy(), block_card(), branch_ifsc(), cheque_status(), fund_transfer(), get_balance() (+11 more)

### Community 8 - "turn.py"
Cohesion: 0.21
Nodes (9): SIMULATED core banking. Registered as SIMULATED in capabilities.py, and the…, Customers, voice enrolments and caller identification, all persistent. The…, datetime, ComplianceTrace: the spine. One trace per turn, threaded through every stage.…, utcnow(), The turn orchestrator: one ComplianceTrace threaded through every stage. This…, sqlite3, typing (+1 more)

### Community 9 - "pii.py"
Cohesion: 0.10
Nodes (34): demo(), find_spoken_digit_runs(), luhn_check(), luhn_checkdigit(), A7. PII detection and tokenisation, run before anything touches disk. Two…, Returns (char_start, char_end, digits) for runs of >= MIN_SPOKEN_DIGITS…, Replace every detected identifier with a stable token. `counters` and `seen`…, Mod-10 checksum. Double every second digit from the right, subtract 9 from any… (+26 more)

### Community 10 - "Substitution rule"
Cohesion: 0.08
Nodes (33): CPU-only dependency constraint, FastAPI, faster-whisper, kokoro-onnx, piper-tts, scikit-learn, sentence-transformers, Spoken digit recovery (+25 more)

### Community 11 - "test_scenarios.py"
Cohesion: 0.12
Nodes (24): Run a voice check and store the outcome on the session. This is the only thing…, record_verification(), ask(), fixture, P2 acceptance: all ten demo beats, in text mode, as one file. This is the…, The fix for the bug the recording caught: the assistant used to score a seeded…, A check is evidence about who is speaking now, so it runs out., Picking a customer with no seeded voice used to raise FileNotFoundError on the… (+16 more)

### Community 12 - "langid.py"
Cohesion: 0.11
Nodes (27): code_mix_index(), demo(), identify(), _is_devanagari(), _is_perso_arabic(), merge_spans(), A1. Code-switch-aware language identification. Per-word language evidence is…, Best language path under the switch penalty. Returns one label per word. (+19 more)

### Community 13 - "test_tts_language.py"
Cohesion: 0.13
Nodes (21): line(), demo(), _en_below_thousand(), _hi_below_thousand(), _mr_below_thousand(), Turning values into words a synthesiser can say naturally. Piper is an espeak-…, An amount in Indian numbering, as words. 206465.68 in English becomes 'two lakh…, Last pass before synthesis. Spells out acronyms a synthesiser would otherwise… (+13 more)

### Community 14 - "config.py"
Cohesion: 0.12
Nodes (17): argparse, _load_calibration(), _load_dotenv(), Every tunable number in the system lives here. Rule for this file: if a value…, Read .env before anything else looks at the environment. The CLU provider key…, Overlay measured values written by `make eval` / scripts/calibrate.py. Keeps…, os, pathlib (+9 more)

### Community 15 - "Contextual language understanding layer"
Cohesion: 0.13
Nodes (25): Indian-numbering amount parsing, Code-mix index, A1 code-switch-aware language identification, A2 geometric confidence fusion, Seed intent utterance bank, A3 intent classification, Rule-based slot extraction, Script and lexicon posterior prior (+17 more)

### Community 16 - "test_investment.py"
Cohesion: 0.14
Nodes (21): investment_advice(), investment_info(), Facts about a customer's own investments, or about a product. Everything here…, Refuse, explain, and hand to someone licensed to answer. Not a hedged answer. A…, blank_trace(), core(), fixture, parametrize (+13 more)

### Community 17 - "test_api.py"
Cohesion: 0.11
Nodes (21): client(), fixture, parametrize, Section 8. The HTTP contract and the authorisation boundary on it. These tests…, A throwaway database per test. main.DB_PATH is patched rather than main.CONN,…, The single most important cell in the role matrix., test_an_anonymous_call_is_identified_over_http(), test_compliance_officer_can_export_the_ledger() (+13 more)

### Community 18 - "Compliance-Aware Multilingual Voice Assistant for BFSI"
Cohesion: 0.15
Nodes (22): graphify skill directive, graphify query workflow, Ledger checkpoints, Three independent ledger checks, A8 tamper-evident hash-chain ledger, Tamper localisation, Layer 3, compliance, ComplianceTrace (+14 more)

### Community 19 - "test_clu.py"
Cohesion: 0.13
Nodes (21): enabled(), Whether this turn is worth a model call. Most turns are not. A confident,…, should_call(), get_provider(), provider_names(), parametrize, The contextual language layer. Most of this file is about what the CLU is NOT…, Explicitly disabled, not "whatever .env happens to say": this test used to… (+13 more)

### Community 20 - "nlu.py"
Cohesion: 0.16
Nodes (16): cosine(), encode(), get_model(), model_id(), ndarray, One sentence-transformer, loaded once, shared by the NLU head and retrieval.…, Prefer the pre-downloaded local copy so a demo launch never touches the…, Cosine similarity of a single vector against a matrix of row vectors. (+8 more)

### Community 21 - "merge_with_baseline"
Cohesion: 0.16
Nodes (17): CLUOutcome, merge_with_baseline(), Combine the two readings under the safety floor. The rule: the CLU may raise…, Everything the trace needs to explain what the language layer did., outcome(), Rule-based extraction is auditable; model output is not., The single most important test in this file., The deterministic head fired fraud_report at 0.30 on the harmless follow-up… (+9 more)

### Community 22 - "A7 PII redaction before persistence"
Cohesion: 0.15
Nodes (20): PyJWT, Demo environment secrets, Consent withdrawal purge, Intent sensitivity table, Luhn mod-10 check, A7 PII redaction before persistence, Per-session token map and AES-256-GCM vault, Verhoeff dihedral check (+12 more)

### Community 23 - "A5 risk scoring"
Cohesion: 0.16
Nodes (20): Silero VAD, Log-scaled amount normalisation, Saturating anomaly deviation term, The automation gate, Lowest floor meeting a precision constraint, Four-tier risk ladder, Per-intent minimum tier, Maximal marginal relevance (+12 more)

### Community 24 - "ProviderReply"
Cohesion: 0.15
Nodes (13): _extract_json(), Models fence their JSON, prefix it, or append an apology. Take the first…, The one entry point. Everything above this is provider-agnostic. Never raises.…, understand_turn(), ProviderReply, What a provider hands back, before schema validation., test_a_provider_that_raises_does_not_break_the_turn(), test_conversation_context_is_bounded() (+5 more)

### Community 25 - "extract"
Cohesion: 0.19
Nodes (16): demo(), extract(), parse_amount(), A3, second half. Slot extraction by rule, not by model. Rules are auditable,…, All slots for one utterance. Only non-empty slots are returned, so the trace…, Digits first, then word numbers. Returns None when no amount is present., test_phone_number_is_never_parsed_as_an_amount(), parametrize (+8 more)

### Community 26 - "Intent: product_info"
Cohesion: 0.14
Nodes (18): Basic Savings Bank Deposit Account, Deposit Account Nomination, POL-ACC-013 Account Opening and Types v1.6, Salary Account, Nigdi Branch (DEMO0001234), POL-FD-009 Fixed Deposit Schemes and Rates v3.2, Premature Withdrawal Penalty, Senior Citizen Rate Benefit (+10 more)

### Community 27 - "CLUResult"
Cohesion: 0.12
Nodes (13): CLUResult, BaseModel, The contract between the language layer and the banking layer. Everything the…, Structured understanding of one turn., test_confidence_is_clamped(), test_free_text_fields_are_bounded(), test_sub_intent_cannot_duplicate_the_primary(), test_two_languages_implies_code_mixed() (+5 more)

### Community 28 - "Ten-beat demo script"
Cohesion: 0.17
Nodes (17): SpeechBrain, Anti-spoofing BASELINE countermeasure, ECAPA-TDNN enrolment, LFCC and GMM log-likelihood ratio, A6 speaker verification, Verification expiry and the SIMULATED fallback, Conflict C3, AASIST downgraded to a baseline, Demo persona CUST9001 (+9 more)

### Community 29 - "api.ts"
Cohesion: 0.15
Nodes (19): api, AuthOutcome, CallDetail, CallFilters, CallRow, Capability, getToken(), LanguageSpan (+11 more)

### Community 30 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+8 more)

### Community 31 - "dialogue.py"
Cohesion: 0.16
Nodes (15): dev_history(), norm_amount(), A2 and A5. Confidence fusion, risk scoring, tier assignment, and the policy…, min(1, log1p(a) / log1p(A_max)). Log scale because the step from 1,000 to…, 1 - exp(-lam * n). Saturating, so a session with six anomalies is not treated…, Whether knowing who is speaking matters for this intent. Public information…, R = w1*sens + w2*norm(amount) + w3*(1 - s_verify) + w4*dev(history). Returns…, requires_identity() (+7 more)

### Community 32 - "Measured results"
Cohesion: 0.23
Nodes (16): api container service, Measured calibration file, Entity-level error rate, A9 evaluation metrics, Hand-labelled evaluation set, Normalised minimum t-DCF, Word error rate with Levenshtein alignment, Anti-spoof measurement compares two synthesis conditions (+8 more)

### Community 33 - "Seeded Intent Bank (A3 intent head)"
Cohesion: 0.21
Nodes (15): Card Block, POL-CRD-002 Debit and Credit Card Blocking v2.3, Unauthorised Transaction Liability Ladder, Cheque Truncation System Clearing, POL-CHQ-003 Cheque Collection and Clearing v1.4, Stop Payment Instruction, Fixed Deposit Interest Rate Slabs, Savings Interest Rate Slabs (+7 more)

### Community 34 - "harness.py"
Cohesion: 0.24
Nodes (11): load_set(), `make eval` runs this. It regenerates every number in docs/RESULTS.md from…, Dominant-language accuracy plus the CMI distribution. Code-mixed utterances are…, Calibrate the refusal floor on the split that actually matters. The negative…, render_markdown(), _row(), run_all(), run_langid() (+3 more)

### Community 35 - "POL-FEE-007 Schedule of Fees and Charges v4.1"
Cohesion: 0.20
Nodes (14): IFSC Code, Replacement Card Issuance, Cheque Return Charges, ATM Transaction Charges, Debit Card Charges, Fund Transfer Charges, POL-FEE-007 Schedule of Fees and Charges v4.1, Daily ATM and POS Limits (+6 more)

### Community 36 - "clu_harness.py"
Cohesion: 0.24
Nodes (12): _delta(), _entities_match(), load_cases(), Baseline against baseline-plus-CLU, on the cases the baseline is expected to…, Every expected entity present and equal. Extra entities are allowed: over-…, The deterministic classifier alone, exactly as the frozen snapshot., Deterministic classifier, then the CLU on the turns the router picks. `pace_s`…, render() (+4 more)

### Community 37 - "test_metrics.py"
Cohesion: 0.11
Nodes (22): corpus_wer(), demo(), entity_error_rate(), normalize_tokens(), WER = (S + D + I) / N., Pooled WER over a corpus, which is the correct aggregate. Averaging per-…, EER_s = (1/|E|) * sum 1[e_hat != e], per entity type and overall. Each…, wer() (+14 more)

### Community 38 - "retrieval.py"
Cohesion: 0.16
Nodes (18): build_index(), chunk_document(), _index(), _is_current(), mmr_select(), parse_front_matter(), ndarray, Path (+10 more)

### Community 39 - "POL-HL-001 Home Loan Interest Rates v1.1 (current)"
Cohesion: 0.23
Nodes (13): Home Loan Rate Slabs (FY 2025-26), Loan to Value Ratio Cap, POL-HL-001 Home Loan Interest Rates v1.0 (superseded), Home Loan Processing Fee (0.35 percent), Home Loan Rate Slabs (from 1 April 2026), POL-HL-001 Home Loan Interest Rates v1.1 (current), Home Loan Processing Fee (0.30 percent), Women Applicant Concession (5 bps) (+5 more)

### Community 40 - "Automated Investment Advice Refusal"
Cohesion: 0.27
Nodes (13): Automated Investment Advice Refusal, Past Performance Disclaimer, POL-INV-016 Investment Advice and the Limits of Automated Service v1.0, Registered Investment Adviser, SEBI (Investment Advisers) Regulations 2013, Suitability and Risk Profiling, Demat Account Charges and Brokerage, POL-INV-015 Investment Services, Demat and Mutual Funds v1.0 (+5 more)

### Community 41 - "Decision log"
Cohesion: 0.10
Nodes (19): D10. The session tier ratchet needed three guards, D11. Not every tier 3 is a risk signal, D14. The similarity floor was calibrated against the wrong negative class, D15. Verification expires, D16. The CLU may raise risk and never lower it, D17. Cloud CLU breaks the on-premise claim, and that is recorded per turn, D18. Voice-first UI deferred, D19. Graphify ignore list is a privacy control (+11 more)

### Community 42 - "generate.py"
Cohesion: 0.36
Nodes (14): matplotlib, matplotlib_patches, matplotlib_pyplot, arrow(), box(), canvas(), fig_layers(), fig_ledger() (+6 more)

### Community 43 - "Hard tier 3 override"
Cohesion: 0.24
Nodes (12): Hard tier 3 override, Ratchet guards, Session tier ratchet, Investment advice boundary, NON_RATCHETING_TIER3 carve-out, SEBI Investment Advisers Regulations 2013, Four defects found by a recorded session, Downgrade carve-out for unconfident hard-handover readings (+4 more)

### Community 44 - "TraceView.tsx"
Cohesion: 0.26
Nodes (8): AuthPanel(), LanguagePanel(), num(), pct(), RetrievalPanel(), RiskPanel(), StageTimeline(), TraceView()

### Community 45 - "assign_tier"
Cohesion: 0.18
Nodes (11): assign_tier(), Tier is the maximum of three things: what the score says, what the intent's own…, tier_from_score(), test_advice_can_never_be_automated_whatever_the_score(), Without the public-intent rule every unverified turn scores at least 0.25 = t1…, One misheard turn used to make the assistant refuse to quote its own published…, test_account_intents_still_pay_the_verification_term(), test_public_information_can_reach_tier_zero() (+3 more)

### Community 46 - "package.json"
Cohesion: 0.14
Nodes (13): name, private, scripts, build, dev, preview, type, version (+5 more)

### Community 47 - "MockProvider"
Cohesion: 0.20
Nodes (5): MockProvider, NullProvider, Offline stand-in with no model behind it. It exists so the plumbing, the…, test_hosted_provider_declares_that_data_leaves_the_machine(), test_mock_provider_reads_a_compound_code_mixed_request()

### Community 48 - "main.tsx"
Cohesion: 0.20
Nodes (7): Customer, Trace, Compliance(), Msg, frontend_src_styles, react-dom, react-router-dom

### Community 49 - "speaker.py"
Cohesion: 0.26
Nodes (14): eer(), embed_audio(), _encoder(), enrol(), get_enrolment(), model_id(), Connection, ndarray (+6 more)

### Community 50 - "gate"
Cohesion: 0.22
Nodes (8): ceiling_for(), gate(), The R below which a turn at this tier may be automated. Tier 3 has none., Automate only when every condition holds. Otherwise refuse or escalate. The…, tau_for(), test_gate_refuses_when_ungrounded(), test_gate_reports_the_first_failing_condition(), test_tier3_tau_is_unreachable()

### Community 51 - "test_risk.py"
Cohesion: 0.25
Nodes (7): fuse_confidence(), c_final = c_asr^alpha * c_intent^beta * c_retr^gamma. Geometric, not…, A2 and A5. Deterministic, so exact values, plus the property test the paper…, An average would let a confident intent hide a terrible transcript., test_fusion_exponents_sum_to_one(), test_fusion_is_geometric_and_vetoable(), random

### Community 52 - "ratchet_applies"
Cohesion: 0.25
Nodes (9): ratchet_applies(), Whether the session floor binds this turn. Public-information intents are…, parametrize, A confident identity must not be able to skip the read-back on an action that…, A scoring bug must never be able to automate a fraud report., test_account_intents_are_not_ratchet_exempt(), test_hard_override_beats_any_score(), test_intent_floor_holds_even_with_perfect_verification() (+1 more)

### Community 53 - "test_call_state.py"
Cohesion: 0.06
Nodes (54): BadTransition, begin_turn(), Call, CallEnded, Cancelled, CancelToken, end_call(), finish_turn() (+46 more)

### Community 54 - "POL-GRV-005 Grievance Redressal and Escalation v2.0"
Cohesion: 0.33
Nodes (9): National Cybercrime Reporting Portal Reference, Human-Only Fraud Report Handling, POL-FRD-012 Fraud Reporting and Customer Protection v2.5, Shadow Credit Pending Investigation, Reserve Bank Integrated Ombudsman Scheme, Nodal Officer (Regional Office), POL-GRV-005 Grievance Redressal and Escalation v2.0, Principal Nodal Officer (Head Office) (+1 more)

### Community 55 - "providers.py"
Cohesion: 0.13
Nodes (15): _coordinates_two_asks(), Contextual Language Understanding. What it is for: real speech is code-mixed,…, A coordinator with real content on both sides. Bare "and" is too common to…, build_user_prompt(), example_messages(), The prompt, versioned and kept small. PROMPT_VERSION goes into every trace and…, The turn, plus a bounded slice of what came before it., Two shots, for the two things a small model gets wrong without them. (+7 more)

### Community 56 - "models.py"
Cohesion: 0.07
Nodes (38): alembic, _common(), Alembic environment. The database URL comes from the application config, not…, run_migrations_offline(), run_migrations_online(), AccessLog, Account, Agent (+30 more)

### Community 57 - "POL-BRN-006 Branch Network and IFSC Codes v1.2"
Cohesion: 0.33
Nodes (7): Andheri East Branch (DEMO0002101), Branch Timings, Hadapsar Branch (DEMO0001236), Kothrud Branch (DEMO0001235), Nashik Road Branch (DEMO0003301), POL-BRN-006 Branch Network and IFSC Codes v1.2, Intent: branch_ifsc

### Community 58 - "needs_grounding"
Cohesion: 0.33
Nodes (6): needs_grounding(), Whether to search the policy knowledge base for this intent., Whether an empty retrieval result must block the answer. Stricter than…, runs_retrieval(), A cheque status comes from the cheque table, so an empty policy search must not…, test_retrieval_and_grounding_are_different_questions()

### Community 59 - "POL-KYC-004 Know Your Customer Requirements v3.0"
Cohesion: 0.40
Nodes (6): Video KYC Onboarding, Demat and Trading Account, Incomplete KYC Account Restrictions, Officially Valid Document, Periodic KYC Updation by Risk Tier, POL-KYC-004 Know Your Customer Requirements v3.0

### Community 60 - "devDependencies"
Cohesion: 0.33
Nodes (6): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react

### Community 61 - "test_compliance_lookup.py"
Cohesion: 0.09
Nodes (37): customer_summary(), call_detail(), customer_detail(), ledger_for_call(), list_cases(), Connection, R2. What a compliance officer can look up, and the record of them doing it. The…, Call summaries, newest first, filtered. `decision` and `tier` filter on the… (+29 more)

### Community 62 - "require"
Cohesion: 0.15
Nodes (37): One access_log row and one ledger record per look. The ledger payload carries…, record_access(), access_log(), call_detail(), call_recordings(), call_state(), conn(), customer_calls() (+29 more)

### Community 63 - "ratchet_should_raise"
Cohesion: 0.50
Nodes (4): ratchet_should_raise(), Whether THIS turn is allowed to raise the session floor. A turn escalates on…, A garbled transcript should escalate the turn and leave the call usable., test_a_low_confidence_escalation_does_not_pin_the_session()

### Community 64 - "test_recompute_from_components_matches_stored_score"
Cohesion: 0.50
Nodes (4): Independent recomputation used by the property test. Reads only what the trace…, recompute_from_components(), The property the paper claims: a reviewer can recompute the decision from the…, test_recompute_from_components_matches_stored_score()

### Community 65 - "dependencies"
Cohesion: 0.50
Nodes (4): dependencies, react, react-dom, react-router-dom

### Community 66 - "pytest"
Cohesion: 0.08
Nodes (30): api(), open_call(), page(), fixture, R3 acceptance, through the browser and through the API the browser uses. The…, A control that exists but is not wired up is what a unit test misses., An authenticated request context against the live server., The double-voice bug. The second utterance supersedes the first, and the first… (+22 more)

### Community 68 - "main.py"
Cohesion: 0.09
Nodes (30): asyncio, A turn is already running and the caller asked not to supersede it., TurnInFlight, _call_error(), call_interrupt(), ConsentRequest, create_consent(), demo_token() (+22 more)

### Community 69 - "crypto.py"
Cohesion: 0.11
Nodes (29): decrypt(), decrypt_bytes(), decrypt_file(), demo(), encrypt(), encrypt_bytes(), encrypt_file(), _key() (+21 more)

### Community 70 - "create_session"
Cohesion: 0.10
Nodes (29): create_customer(), find_by_mobile(), find_customer(), Identify a caller who states their registered mobile number. Matching is on the…, By customer id, or by a stated mobile number., load_clip(), Load a seeded voice clip by name, for the text-fallback demo path., create_session() (+21 more)

### Community 71 - "run_turn"
Cohesion: 0.10
Nodes (30): _conversation_context(), detect_anomalies(), finalise(), scrub(), _fresh_verification(), Row, dev(history) inputs. Each one is a named string so the dashboard can list…, One turn. `cancel` is the token from `call.begin_turn`. It is checked at every… (+22 more)

### Community 72 - "test_persistence.py"
Cohesion: 0.16
Nodes (28): ConsentError, Raised when audio would be stored without a consented, noticed call., Encrypt and store one clip. Raises ConsentError if it may not. The plaintext is…, store(), complete_recording_notice(), Called when the recording notice has finished playing. Until this runs,…, A call with a consented recording, so playback has something to play. Built…, seeded_call() (+20 more)

### Community 73 - "db.py"
Cohesion: 0.14
Nodes (21): db_url(), One place decides where the data lives. Default is the SQLite file. Set…, _alembic_config(), connect(), engine(), init_db(), migrate(), Connection (+13 more)

### Community 74 - "_act"
Cohesion: 0.11
Nodes (21): _cite(), escalate(), need_verification(), _per_lang(), pick(), Build the same sentence in all three languages from one callable., Spoken citation. The document title and version are said aloud; the identifier…, readback() (+13 more)

### Community 75 - "post"
Cohesion: 0.17
Nodes (17): audio_turn(), call_end(), claim_handover(), enroll(), _one_turn(), Hang up. Works in every state, including with a turn in flight., Run the body as the call's single active turn. Yields the cancel token and the…, Run a live voice check for this session. This is the only thing that… (+9 more)

### Community 76 - "recordings.py"
Cohesion: 0.22
Nodes (15): call_may_record(), _iso(), log_access(), purge_call(), purge_expired(), Connection, datetime, Call recording: consent-gated, encrypted, retained, and auditable. Change… (+7 more)

### Community 77 - "status_of"
Cohesion: 0.16
Nodes (10): Status for a component, used to stamp trace stages. Unknown means SIMULATED.…, status_of(), digest(), _input_digest(), Any, Context manager that times a stage and appends its record. Usage: with…, Hash of the stage input. Bytes are hashed directly so audio never lands in the…, _StageCtx (+2 more)

### Community 78 - "metrics.py"
Cohesion: 0.18
Nodes (14): calibrate_delta(), _canonical(), eer(), locate_entity(), min_tdcf(), ndarray, A9. Evaluation metrics, all computed here rather than imported. The Levenshtein…, Normalise a surface form so that the spellings of one value agree. "fifty… (+6 more)

### Community 79 - "prosody.py"
Cohesion: 0.29
Nodes (12): assemble(), breath(), demo(), ndarray, Random, Making synthesised speech breathe. A neural voice handed a whole paragraph…, Synthesise phrase by phrase and join with pauses. `synth(phrase, speed) ->…, Text to (phrase, pause after it in seconds). (+4 more)

### Community 80 - "save_enrollment"
Cohesion: 0.23
Nodes (12): load_enrollment(), Connection, ndarray, The live embedding. Prefers the cache, falls back to decrypting the durable…, Withdraw biometric consent. The row is marked, not deleted, so the withdrawal…, Persist an enrolment. Supersedes any earlier one for this customer., revoke_enrollment(), save_enrollment() (+4 more)

### Community 81 - "e2e/conftest.py"
Cohesion: 0.21
Nodes (11): _free(), fixture, A real browser against a real stack, on its own ports and its own database. The…, stack(), _stop_group(), _wait(), Popen, shutil (+3 more)

### Community 82 - "pipeline/__init__.py"
Cohesion: 0.24
Nodes (9): Transcribe the rendered audio. Skipped, and said to be skipped, when the audio…, run_asr(), _model(), model_id(), ndarray, faster-whisper on CPU, int8. Not fine-tuned on banking audio. The capability…, Returns text plus an honest confidence. Whisper does not emit a calibrated…, transcribe() (+1 more)

### Community 83 - "capabilities.py"
Cohesion: 0.28
Nodes (8): Capability, BaseModel, The honesty registry: the single source of truth for what is real here. A panel…, The CLU's registry entry depends on runtime configuration, so it is recomputed…, refresh_clu(), registry_dict(), capabilities(), The honesty registry. Deliberately unauthenticated: anybody looking at this…

### Community 84 - "OpenAICompatibleProvider"
Cohesion: 0.33
Nodes (4): OpenAICompatibleProvider, Groq, OpenRouter, Together, vLLM, Gemini's compatibility endpoint. The…, test_hosted_provider_without_a_key_fails_cleanly(), test_the_api_key_never_appears_in_a_provider_reply()

### Community 85 - "classify"
Cohesion: 0.33
Nodes (7): run_nlu(), classify(), _head(), model_id(), Intent plus slots. One call, one record in the trace., Returns intent, posterior, and the full ranking for the trace. The runner-up…, understand()

### Community 86 - "align"
Cohesion: 0.29
Nodes (4): align(), Alignment, Hypothesis token indices covering reference tokens [start, end). Insertions…, Levenshtein alignment with backpointers. O(|ref| * |hyp|).

### Community 87 - "app/__init__.py"
Cohesion: 0.33
Nodes (5): conn(), live(), fixture, An empty, migrated database. No customers, no accounts, no models., A seeded database plus the real models. Uses the project runtime, since the…

### Community 88 - "assert_devanagari"
Cohesion: 0.29
Nodes (7): assert_devanagari(), Guard against a romanised Hindi or Marathi reply reaching the voice. Raises…, The guard that makes the rule enforced rather than remembered., Names, reference codes and IFSC codes stay Latin inside a Hindi reply., test_tts_guard_tolerates_embedded_latin(), test_tts_refuses_to_speak_romanised_hindi(), D13. Hindi and Marathi replies are written in Devanagari

### Community 89 - "text_turn"
Cohesion: 0.33
Nodes (6): The text fallback. Everything after the transcript is identical to the voice…, Audio in, partial transcript and reply out. Protocol, deliberately small:…, _record_metrics(), text_turn(), ws_session(), websocket

### Community 90 - "vad.py"
Cohesion: 0.53
Nodes (5): _energy_gate(), ndarray, Silero VAD endpointing. Trims leading and trailing silence before ASR so the…, _silero(), trim_to_speech()

### Community 92 - "latency_from_traces"
Cohesion: 0.50
Nodes (3): latency_from_traces(), p50 and p95 per stage, straight off the trace timings., test_latency_percentiles()

### Community 93 - "_sqlite_path_from_url"
Cohesion: 0.67
Nodes (3): Path, The file a SQLite URL points at, or None for any other dialect., _sqlite_path_from_url()

## Ambiguous Edges - Review These
- `FastAPI` → `Frontend single-page app shell`  [AMBIGUOUS]
  frontend/index.html · relation: shares_data_with
- `Data residency trade-off` → `DPDP Act 2023 and DPDP Rules`  [AMBIGUOUS]
  docs/CLU.md · relation: conceptually_related_to
- `Intent sensitivity table` → `Obligation, purpose limitation`  [AMBIGUOUS]
  docs/COMPLIANCE_MAPPING.md · relation: conceptually_related_to

## Knowledge Gaps
- **80 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+75 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 537 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `FastAPI` and `Frontend single-page app shell`?**
  _Edge tagged AMBIGUOUS (relation: shares_data_with) - confidence is low._
- **What is the exact relationship between `Data residency trade-off` and `DPDP Act 2023 and DPDP Rules`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Intent sensitivity table` and `Obligation, purpose limitation`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `run_turn()` connect `run_turn` to `ledger.py`, `MockCore`, `ComplianceTrace`, `turn.py`, `test_scenarios.py`, `langid.py`, `test_clu.py`, `merge_with_baseline`, `ProviderReply`, `dialogue.py`, `retrieval.py`, `assign_tier`, `speaker.py`, `gate`, `test_risk.py`, `needs_grounding`, `crypto.py`, `create_session`, `test_persistence.py`, `_act`, `pipeline/__init__.py`, `classify`, `text_turn`, `vad.py`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `MockCore` connect `MockCore` to `seed_data.py`, `run_turn`, `turn.py`, `ComplianceTrace`, `_act`, `test_investment.py`, `test_call_state.py`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `CLUResult` connect `CLUResult` to `MockProvider`, `test_clu.py`, `merge_with_baseline`, `providers.py`, `ProviderReply`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MockCore` (e.g. with `add_payee()` and `block_card()`) actually correct?**
  _`MockCore` has 16 INFERRED edges - model-reasoned connections that need verification._