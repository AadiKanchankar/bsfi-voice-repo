# Graph Report - Projectdemo  (2026-09-22)

## Corpus Check
- 133 files · ~132,813 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 13 file(s) not represented in the graph (top: (none) 8, .ini 2, .example 1)

## Summary
- 2049 nodes · 4517 edges · 114 communities (102 shown, 12 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 232 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `abd3398d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ledger.py
- test_rbac.py
- seed_data.py
- crypto.py
- tts.py
- antispoof.py
- MockCore
- ComplianceTrace
- append
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
- extract
- merge_with_baseline
- A7 PII redaction before persistence
- A5 risk scoring
- ProviderReply
- test_voice_style.py
- Intent: product_info
- CLUResult
- Ten-beat demo script
- api.ts
- compilerOptions
- risk_score
- Measured results
- Seeded Intent Bank (A3 intent head)
- harness.py
- POL-FEE-007 Schedule of Fees and Charges v4.1
- clu/__init__.py
- test_metrics.py
- retrieval.py
- POL-HL-001 Home Loan Interest Rates v1.1 (current)
- Automated Investment Advice Refusal
- Decision log
- generate.py
- Hard tier 3 override
- TraceView.tsx
- test_risk.py
- package.json
- MockProvider
- main.tsx
- speaker.py
- dialogue.py
- fuse_confidence
- ratchet_applies
- test_call_state.py
- POL-GRV-005 Grievance Redressal and Escalation v2.0
- clu/providers.py
- models.py
- POL-BRN-006 Branch Network and IFSC Codes v1.2
- needs_grounding
- POL-KYC-004 Know Your Customer Requirements v3.0
- devDependencies
- test_compliance_lookup.py
- require
- ratchet_should_raise
- test_recompute_from_components_matches_stored_score
- clu_harness.py
- test_dashboard.py
- cryptography
- main.py
- nlu.py
- create_customer
- run_turn
- test_persistence.py
- db.py
- test_speech_normaliser.py
- Depends
- turn.py
- trace.py
- metrics.py
- scripts
- create_session
- e2e/conftest.py
- verify
- capabilities.py
- test_providers.py
- _KeyedProvider
- Alignment
- pytest
- pipeline/providers.py
- call_interrupt
- asr.py
- Provider
- latency_from_traces
- text_turn
- RetrievedPassage
- TTSProvider
- speak
- OpenAICompatibleProvider
- Customer.tsx
- Usage
- _clean
- Recording script: English
- Recording script: Hindi
- Recording script: Code-mixed (Hinglish)
- Recording script: Marathi
- init_db
- listening_check.py
- session
- NotWhitelisted
- dev_history
- call_state
- kb_documents
- protective_actions
- speak_plan

## God Nodes (most connected - your core abstractions)
1. `run_turn()` - 58 edges
2. `MockCore` - 51 edges
3. `require()` - 49 edges
4. `utcnow()` - 48 edges
5. `conn()` - 44 edges
6. `ComplianceTrace` - 43 edges
7. `Decision log` - 42 edges
8. `append()` - 39 edges
9. `create_session()` - 35 edges
10. `verify()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `D11. Not every tier 3 is a risk signal` --references--> `investment_advice()`  [INFERRED]
  docs/DECISIONS.md → backend/app/banking/actions.py
- `D14. The similarity floor was calibrated against the wrong negative class` --references--> `out_of_scope()`  [INFERRED]
  docs/DECISIONS.md → backend/app/banking/actions.py
- `D35. The system was not over-escalating on confidence, and the escalation rate was inflated` --references--> `clarify()`  [INFERRED]
  docs/DECISIONS.md → backend/app/banking/actions.py
- `D24. BFSI_DB_URL pointed the migrations and the reads at different files` --references--> `db_url()`  [INFERRED]
  docs/DECISIONS.md → backend/app/config.py
- `D20. SQLModel and Alembic replace hand-written SQL DDL` --references--> `migrate()`  [INFERRED]
  docs/DECISIONS.md → backend/app/db.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The four architectural layers** — docs_architecture_voice_and_ai_layer, docs_architecture_integration_middleware_layer, docs_architecture_compliance_layer, docs_architecture_dashboard_layer, docs_architecture_four_layer_architecture [EXTRACTED 1.00]
- **Home Loan Rate Policy Version Chain (POL-HL-001)** — data_policy_kb_home_loan_rates_v1_pol_hl_001, data_policy_kb_home_loan_rates_v2_pol_hl_001, data_policy_kb_home_loan_rates_v1_interest_rate_slabs, data_policy_kb_home_loan_rates_v2_interest_rate_slabs, data_policy_kb_home_loan_rates_v1_processing_fee, data_policy_kb_home_loan_rates_v2_processing_fee, data_policy_kb_loan_eligibility_home_loan_eligibility [EXTRACTED 1.00]
- **Enforced risk-tier safety properties** — docs_algorithms_hard_tier_override, docs_algorithms_session_tier_ratchet, docs_algorithms_ratchet_guards, docs_algorithms_min_tier_by_intent, docs_algorithms_four_tier_ladder, docs_algorithms_automation_gate [EXTRACTED 1.00]
- **Stages of one audited turn** — docs_algorithms_code_switch_language_identification, docs_algorithms_intent_classification, docs_algorithms_retrieval_grounding, docs_algorithms_confidence_fusion, docs_algorithms_speaker_verification, docs_algorithms_risk_scoring, docs_algorithms_automation_gate, docs_algorithms_pii_redaction, docs_algorithms_tamper_evident_ledger [EXTRACTED 1.00]
- **Compromised Card Response Flow** — data_seed_intent_bank_block_card, data_seed_intent_bank_fraud_report, data_policy_kb_card_blocking_card_block, data_policy_kb_card_blocking_unauthorised_transaction_liability, data_policy_kb_card_blocking_replacement_card, data_policy_kb_fraud_reporting_shadow_credit, data_policy_kb_fraud_reporting_cybercrime_portal_reference [INFERRED 0.85]
- **Refusal and Human Handoff Path** — data_seed_intent_bank_out_of_scope, data_seed_intent_bank_investment_advice, data_seed_intent_bank_agent_request, data_policy_kb_investment_advice_policy_investment_advice_refusal, data_policy_kb_fraud_reporting_fraud_report_handling, data_policy_kb_investment_advice_policy_suitability_and_risk_profiling [INFERRED 0.85]

## Communities (114 total, 12 thin omitted)

### Community 0 - "ledger.py"
Cohesion: 0.16
Nodes (22): _check_record(), _checkpoints(), compute_hash(), export(), head(), _key(), Connection, Row (+14 more)

### Community 1 - "test_rbac.py"
Cohesion: 0.13
Nodes (21): allowed(), current_principal(), decode_token(), issue_token(), Demo-scale RBAC: signed JWT, four hardcoded roles. The production design in the…, _dep(), parametrize, Section 8. The role matrix, walked cell by cell. The cell that matters most: a… (+13 more)

### Community 2 - "seed_data.py"
Cohesion: 0.19
Nodes (18): mask_mobile(), Store and show the last four only. A registered mobile is an identifier; the…, _channel(), luhn_card(), luhn_card_ending(), main(), ndarray, Random (+10 more)

### Community 3 - "crypto.py"
Cohesion: 0.06
Nodes (57): decode(), _decode_container(), duration_s(), _is_container(), ndarray, Audio helpers shared by VAD, ASR, speaker verification and anti-spoofing.…, Bytes to float32 mono at SAMPLE_RATE. Handles WAV directly, anything else…, Decode a compressed container with PyAV, resampling to mono 16 kHz. PyAV ships… (+49 more)

### Community 4 - "tts.py"
Cohesion: 0.07
Nodes (49): load_items(), _pct(), _plan(), Any, R4, first half: measure before touching anything. The existing latency table in…, `per_language` turns for each path, cycling the clips if there are fewer than…, Time the audio path. Returns per-language and overall summaries. `clu` is off…, render_markdown() (+41 more)

### Community 5 - "antispoof.py"
Cohesion: 0.15
Nodes (18): run_biometrics(), AntiSpoofScorer, _deltas(), lfcc(), LfccGmmScorer, _linear_filterbank(), model_id(), ndarray (+10 more)

### Community 6 - "MockCore"
Cohesion: 0.07
Nodes (14): MockCore, Connection, Current value, cost and unrealised gain. Facts only: nothing here is a view on…, Match on the words of the question, not the whole sentence. A LIKE pattern…, core(), fixture, The mock core banking layer. SIMULATED, but its lookups still have to work., A LIKE pattern built from the entire utterance matches nothing, which silently… (+6 more)

### Community 7 - "ComplianceTrace"
Cohesion: 0.13
Nodes (33): add_payee(), _amt(), answer_from_policy(), block_card(), branch_ifsc(), cheque_status(), clarify(), escalate() (+25 more)

### Community 8 - "append"
Cohesion: 0.06
Nodes (57): accept_case(), agent_reply(), available_actions(), case_reference(), close_case(), hold_update(), intake_questions(), offer_callback() (+49 more)

### Community 9 - "pii.py"
Cohesion: 0.10
Nodes (33): demo(), find_spoken_digit_runs(), luhn_check(), luhn_checkdigit(), A7. PII detection and tokenisation, run before anything touches disk. Two…, Returns (char_start, char_end, digits) for runs of >= MIN_SPOKEN_DIGITS…, Replace every detected identifier with a stable token. `counters` and `seen`…, Mod-10 checksum. Double every second digit from the right, subtract 9 from any… (+25 more)

### Community 10 - "Substitution rule"
Cohesion: 0.08
Nodes (33): CPU-only dependency constraint, FastAPI, faster-whisper, kokoro-onnx, piper-tts, scikit-learn, sentence-transformers, Spoken digit recovery (+25 more)

### Community 11 - "test_scenarios.py"
Cohesion: 0.16
Nodes (19): Run a voice check and store the outcome on the session. This is the only thing…, record_verification(), ask(), P2 acceptance: all ten demo beats, in text mode, as one file. This is the…, The fix for the bug the recording caught: the assistant used to score a seeded…, A check is evidence about who is speaking now, so it runs out., Picking a customer with no seeded voice used to raise FileNotFoundError on the…, The ratchet stops an attacker lowering their own risk before touching an… (+11 more)

### Community 12 - "langid.py"
Cohesion: 0.05
Nodes (51): code_mix_index(), demo(), identify(), _is_devanagari(), _is_perso_arabic(), merge_spans(), A1. Code-switch-aware language identification. Per-word language evidence is…, Best language path under the switch penalty. Returns one label per word. (+43 more)

### Community 13 - "test_tts_language.py"
Cohesion: 0.10
Nodes (29): line(), readback_summary(), demo(), _en_below_thousand(), _group_digits(), _hi_below_thousand(), _mr_below_thousand(), Turning values into words a synthesiser can say naturally. Piper is an espeak-… (+21 more)

### Community 14 - "config.py"
Cohesion: 0.10
Nodes (20): argparse, _load_calibration(), _load_dotenv(), Path, Every tunable number in the system lives here. Rule for this file: if a value…, Read .env before anything else looks at the environment. The CLU provider key…, The file a SQLite URL points at, or None for any other dialect., Overlay measured values written by `make eval` / scripts/calibrate.py. Keeps… (+12 more)

### Community 15 - "Contextual language understanding layer"
Cohesion: 0.13
Nodes (25): Indian-numbering amount parsing, Code-mix index, A1 code-switch-aware language identification, A2 geometric confidence fusion, Seed intent utterance bank, A3 intent classification, Rule-based slot extraction, Script and lexicon posterior prior (+17 more)

### Community 16 - "test_investment.py"
Cohesion: 0.12
Nodes (21): investment_advice(), investment_info(), Facts about a customer's own investments, or about a product. Everything here…, Refuse, explain, and hand to someone licensed to answer. Not a hedged answer. A…, blank_trace(), core(), fixture, parametrize (+13 more)

### Community 17 - "test_api.py"
Cohesion: 0.12
Nodes (20): client(), fixture, parametrize, Section 8. The HTTP contract and the authorisation boundary on it. These tests…, A throwaway database per test. main.DB_PATH is patched rather than main.CONN,…, The single most important cell in the role matrix., test_an_anonymous_call_is_identified_over_http(), test_compliance_officer_can_export_the_ledger() (+12 more)

### Community 18 - "Compliance-Aware Multilingual Voice Assistant for BFSI"
Cohesion: 0.15
Nodes (22): graphify skill directive, graphify query workflow, Ledger checkpoints, Three independent ledger checks, A8 tamper-evident hash-chain ledger, Tamper localisation, Layer 3, compliance, ComplianceTrace (+14 more)

### Community 19 - "test_clu.py"
Cohesion: 0.15
Nodes (19): enabled(), Whether this turn is worth a model call. Most turns are not. A confident,…, should_call(), get_provider(), provider_names(), The contextual language layer. Most of this file is about what the CLU is NOT…, Explicitly disabled, not "whatever .env happens to say": this test used to…, A single-label head cannot represent the second ask at ANY confidence, so… (+11 more)

### Community 20 - "extract"
Cohesion: 0.19
Nodes (16): demo(), extract(), parse_amount(), A3, second half. Slot extraction by rule, not by model. Rules are auditable,…, All slots for one utterance. Only non-empty slots are returned, so the trace…, Digits first, then word numbers. Returns None when no amount is present., test_phone_number_is_never_parsed_as_an_amount(), parametrize (+8 more)

### Community 21 - "merge_with_baseline"
Cohesion: 0.14
Nodes (19): CLUOutcome, merge_with_baseline(), Combine the two readings under the safety floor. The rule: the CLU may raise…, Everything the trace needs to explain what the language layer did., outcome(), parametrize, Rule-based extraction is auditable; model output is not., The single most important test in this file. (+11 more)

### Community 22 - "A7 PII redaction before persistence"
Cohesion: 0.15
Nodes (20): PyJWT, Demo environment secrets, Consent withdrawal purge, Intent sensitivity table, Luhn mod-10 check, A7 PII redaction before persistence, Per-session token map and AES-256-GCM vault, Verhoeff dihedral check (+12 more)

### Community 23 - "A5 risk scoring"
Cohesion: 0.16
Nodes (20): Silero VAD, Log-scaled amount normalisation, Saturating anomaly deviation term, The automation gate, Lowest floor meeting a precision constraint, Four-tier risk ladder, Per-intent minimum tier, Maximal marginal relevance (+12 more)

### Community 24 - "ProviderReply"
Cohesion: 0.17
Nodes (11): The one entry point. Everything above this is provider-agnostic. Never raises.…, understand_turn(), ProviderReply, What a provider hands back, before schema validation., test_a_provider_that_raises_does_not_break_the_turn(), test_conversation_context_is_bounded(), complete(), test_json_is_recovered_from_a_fenced_response() (+3 more)

### Community 25 - "test_voice_style.py"
Cohesion: 0.09
Nodes (37): asks_if_human(), decorate(), honest_answer(), is_sensitive(), may_use_filler(), phrasing(), pick_filler(), Random (+29 more)

### Community 26 - "Intent: product_info"
Cohesion: 0.14
Nodes (18): Basic Savings Bank Deposit Account, Deposit Account Nomination, POL-ACC-013 Account Opening and Types v1.6, Salary Account, Nigdi Branch (DEMO0001234), POL-FD-009 Fixed Deposit Schemes and Rates v3.2, Premature Withdrawal Penalty, Senior Citizen Rate Benefit (+10 more)

### Community 27 - "CLUResult"
Cohesion: 0.12
Nodes (14): CLUResult, BaseModel, Structured understanding of one turn., An amount must be a number by the time it leaves this layer. The model is free…, Found by the latency harness on live audio, not by a unit test. The model is…, test_a_string_amount_from_the_model_cannot_crash_the_turn(), test_confidence_is_clamped(), test_free_text_fields_are_bounded() (+6 more)

### Community 28 - "Ten-beat demo script"
Cohesion: 0.17
Nodes (17): SpeechBrain, Anti-spoofing BASELINE countermeasure, ECAPA-TDNN enrolment, LFCC and GMM log-likelihood ratio, A6 speaker verification, Verification expiry and the SIMULATED fallback, Conflict C3, AASIST downgraded to a baseline, Demo persona CUST9001 (+9 more)

### Community 29 - "api.ts"
Cohesion: 0.15
Nodes (18): api, AuthOutcome, CallDetail, CallFilters, CallRow, Capability, getToken(), LanguageSpan (+10 more)

### Community 30 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+8 more)

### Community 31 - "risk_score"
Cohesion: 0.18
Nodes (11): norm_amount(), min(1, log1p(a) / log1p(A_max)). Log scale because the step from 1,000 to…, Whether knowing who is speaking matters for this intent. Public information…, R = w1*sens + w2*norm(amount) + w3*(1 - s_verify) + w4*dev(history). Returns…, requires_identity(), risk_score(), test_missing_verification_raises_risk(), test_norm_amount_is_log_scaled() (+3 more)

### Community 32 - "Measured results"
Cohesion: 0.23
Nodes (16): api container service, Measured calibration file, Entity-level error rate, A9 evaluation metrics, Hand-labelled evaluation set, Normalised minimum t-DCF, Word error rate with Levenshtein alignment, Anti-spoof measurement compares two synthesis conditions (+8 more)

### Community 33 - "Seeded Intent Bank (A3 intent head)"
Cohesion: 0.21
Nodes (15): Card Block, POL-CRD-002 Debit and Credit Card Blocking v2.3, Unauthorised Transaction Liability Ladder, Cheque Truncation System Clearing, POL-CHQ-003 Cheque Collection and Clearing v1.4, Stop Payment Instruction, Fixed Deposit Interest Rate Slabs, Savings Interest Rate Slabs (+7 more)

### Community 34 - "harness.py"
Cohesion: 0.21
Nodes (12): load_set(), `make eval` runs this. It regenerates every number in docs/RESULTS.md from…, Dominant-language accuracy plus the CMI distribution. Code-mixed utterances are…, Calibrate the refusal floor on the split that actually matters. The negative…, render_markdown(), _row(), run_all(), run_langid() (+4 more)

### Community 35 - "POL-FEE-007 Schedule of Fees and Charges v4.1"
Cohesion: 0.20
Nodes (14): IFSC Code, Replacement Card Issuance, Cheque Return Charges, ATM Transaction Charges, Debit Card Charges, Fund Transfer Charges, POL-FEE-007 Schedule of Fees and Charges v4.1, Daily ATM and POS Limits (+6 more)

### Community 36 - "clu/__init__.py"
Cohesion: 0.25
Nodes (7): _coordinates_two_asks(), _extract_json(), Contextual Language Understanding. What it is for: real speech is code-mixed,…, Models fence their JSON, prefix it, or append an apology. Take the first…, A coordinator with real content on both sides. Bare "and" is too common to…, The contract between the language layer and the banking layer. Everything the…, re

### Community 37 - "test_metrics.py"
Cohesion: 0.12
Nodes (22): align(), corpus_wer(), demo(), entity_error_rate(), normalize_tokens(), WER = (S + D + I) / N., Pooled WER over a corpus, which is the correct aggregate. Averaging per-…, EER_s = (1/|E|) * sum 1[e_hat != e], per entity type and overall. Each… (+14 more)

### Community 38 - "retrieval.py"
Cohesion: 0.11
Nodes (28): cosine(), encode(), get_model(), model_id(), ndarray, One sentence-transformer, loaded once, shared by the NLU head and retrieval.…, Prefer the pre-downloaded local copy so a demo launch never touches the…, Cosine similarity of a single vector against a matrix of row vectors. (+20 more)

### Community 39 - "POL-HL-001 Home Loan Interest Rates v1.1 (current)"
Cohesion: 0.23
Nodes (13): Home Loan Rate Slabs (FY 2025-26), Loan to Value Ratio Cap, POL-HL-001 Home Loan Interest Rates v1.0 (superseded), Home Loan Processing Fee (0.35 percent), Home Loan Rate Slabs (from 1 April 2026), POL-HL-001 Home Loan Interest Rates v1.1 (current), Home Loan Processing Fee (0.30 percent), Women Applicant Concession (5 bps) (+5 more)

### Community 40 - "Automated Investment Advice Refusal"
Cohesion: 0.27
Nodes (13): Automated Investment Advice Refusal, Past Performance Disclaimer, POL-INV-016 Investment Advice and the Limits of Automated Service v1.0, Registered Investment Adviser, SEBI (Investment Advisers) Regulations 2013, Suitability and Risk Profiling, Demat Account Charges and Brokerage, POL-INV-015 Investment Services, Demat and Mutual Funds v1.0 (+5 more)

### Community 41 - "Decision log"
Cohesion: 0.07
Nodes (26): D10. The session tier ratchet needed three guards, D11. Not every tier 3 is a risk signal, D14. The similarity floor was calibrated against the wrong negative class, D15. Verification expires, D16. The CLU may raise risk and never lower it, D17. Cloud CLU breaks the on-premise claim, and that is recorded per turn, D18. Voice-first UI deferred, D19. Graphify ignore list is a privacy control (+18 more)

### Community 42 - "generate.py"
Cohesion: 0.36
Nodes (14): matplotlib, matplotlib_patches, matplotlib_pyplot, arrow(), box(), canvas(), fig_layers(), fig_ledger() (+6 more)

### Community 43 - "Hard tier 3 override"
Cohesion: 0.24
Nodes (12): Hard tier 3 override, Ratchet guards, Session tier ratchet, Investment advice boundary, NON_RATCHETING_TIER3 carve-out, SEBI Investment Advisers Regulations 2013, Four defects found by a recorded session, Downgrade carve-out for unconfident hard-handover readings (+4 more)

### Community 44 - "TraceView.tsx"
Cohesion: 0.26
Nodes (8): AuthPanel(), LanguagePanel(), num(), pct(), RetrievalPanel(), RiskPanel(), StageTimeline(), TraceView()

### Community 45 - "test_risk.py"
Cohesion: 0.17
Nodes (14): assign_tier(), Tier is the maximum of three things: what the score says, what the intent's own…, tier_from_score(), test_advice_can_never_be_automated_whatever_the_score(), A2 and A5. Deterministic, so exact values, plus the property test the paper…, Without the public-intent rule every unverified turn scores at least 0.25 = t1…, A scoring bug must never be able to automate a fraud report., One misheard turn used to make the assistant refuse to quote its own published… (+6 more)

### Community 46 - "package.json"
Cohesion: 0.13
Nodes (14): dependencies, react, react-dom, react-router-dom, name, private, type, version (+6 more)

### Community 47 - "MockProvider"
Cohesion: 0.20
Nodes (5): MockProvider, NullProvider, Offline stand-in with no model behind it. It exists so the plumbing, the…, test_hosted_provider_declares_that_data_leaves_the_machine(), test_mock_provider_reads_a_compound_code_mixed_request()

### Community 48 - "main.tsx"
Cohesion: 0.19
Nodes (9): NEEDS, Agent(), Compliance(), LANGS, Line, Record(), frontend_src_styles, react (+1 more)

### Community 49 - "speaker.py"
Cohesion: 0.31
Nodes (12): eer(), embed_audio(), _encoder(), enrol(), get_enrolment(), model_id(), Connection, ndarray (+4 more)

### Community 50 - "dialogue.py"
Cohesion: 0.20
Nodes (10): ceiling_for(), gate(), A2 and A5. Confidence fusion, risk scoring, tier assignment, and the policy…, The R below which a turn at this tier may be automated. Tier 3 has none., Automate only when every condition holds. Otherwise refuse or escalate. The…, sens(), tau_for(), test_gate_refuses_when_ungrounded() (+2 more)

### Community 51 - "fuse_confidence"
Cohesion: 0.40
Nodes (5): fuse_confidence(), c_final = c_asr^alpha * c_intent^beta * c_retr^gamma. Geometric, not…, An average would let a confident intent hide a terrible transcript., test_fusion_exponents_sum_to_one(), test_fusion_is_geometric_and_vetoable()

### Community 52 - "ratchet_applies"
Cohesion: 0.33
Nodes (7): ratchet_applies(), Whether the session floor binds this turn. Public-information intents are…, parametrize, A confident identity must not be able to skip the read-back on an action that…, test_account_intents_are_not_ratchet_exempt(), test_intent_floor_holds_even_with_perfect_verification(), test_public_intents_are_ratchet_exempt()

### Community 53 - "test_call_state.py"
Cohesion: 0.06
Nodes (54): BadTransition, begin_turn(), Call, CallEnded, Cancelled, CancelToken, end_call(), finish_turn() (+46 more)

### Community 54 - "POL-GRV-005 Grievance Redressal and Escalation v2.0"
Cohesion: 0.33
Nodes (9): National Cybercrime Reporting Portal Reference, Human-Only Fraud Report Handling, POL-FRD-012 Fraud Reporting and Customer Protection v2.5, Shadow Credit Pending Investigation, Reserve Bank Integrated Ombudsman Scheme, Nodal Officer (Regional Office), POL-GRV-005 Grievance Redressal and Escalation v2.0, Principal Nodal Officer (Head Office) (+1 more)

### Community 55 - "clu/providers.py"
Cohesion: 0.15
Nodes (12): build_user_prompt(), example_messages(), The prompt, versioned and kept small. PROMPT_VERSION goes into every trace and…, The turn, plus a bounded slice of what came before it., Two shots, for the two things a small model gets wrong without them., OllamaProvider, Provider abstraction. The banking pipeline calls `understand_turn`. It does not…, A model running on this machine. Preserves data residency. (+4 more)

### Community 56 - "models.py"
Cohesion: 0.07
Nodes (39): alembic, _common(), Alembic environment. The database URL comes from the application config, not…, run_migrations_offline(), run_migrations_online(), AccessLog, Account, Agent (+31 more)

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
Nodes (39): call_detail(), customer_detail(), ledger_for_call(), list_cases(), Connection, R2. What a compliance officer can look up, and the record of them doing it. The…, Call summaries, newest first, filtered. `decision` and `tier` filter on the…, The list that means nobody has to paste a UUID during a demo. (+31 more)

### Community 62 - "require"
Cohesion: 0.11
Nodes (39): One access_log row and one ledger record per look. The ledger payload carries…, record_access(), access_log(), agent_queue(), call_detail(), call_recordings(), case_intake_questions(), conn() (+31 more)

### Community 63 - "ratchet_should_raise"
Cohesion: 0.50
Nodes (4): ratchet_should_raise(), Whether THIS turn is allowed to raise the session floor. A turn escalates on…, A garbled transcript should escalate the turn and leave the call usable., test_a_low_confidence_escalation_does_not_pin_the_session()

### Community 64 - "test_recompute_from_components_matches_stored_score"
Cohesion: 0.50
Nodes (4): Independent recomputation used by the property test. Reads only what the trace…, recompute_from_components(), The property the paper claims: a reviewer can recompute the decision from the…, test_recompute_from_components_matches_stored_score()

### Community 65 - "clu_harness.py"
Cohesion: 0.24
Nodes (12): _delta(), _entities_match(), load_cases(), Baseline against baseline-plus-CLU, on the cases the baseline is expected to…, Every expected entity present and equal. Extra entities are allowed: over-…, The deterministic classifier alone, exactly as the frozen snapshot., Deterministic classifier, then the CLU on the turns the router picks. `pace_s`…, render() (+4 more)

### Community 66 - "test_dashboard.py"
Cohesion: 0.07
Nodes (31): api(), open_call(), page(), fixture, R3 acceptance, through the browser and through the API the browser uses. The…, The safety rule. Cut off the read-back, then say yes, and nothing must happen:…, A control that exists but is not wired up is what a unit test misses., The change request's number, measured on the page's own player. An earlier… (+23 more)

### Community 68 - "main.py"
Cohesion: 0.08
Nodes (35): asyncio, registry_dict(), agent_close(), agent_say(), AgentReplyRequest, capabilities(), case_intake(), CloseRequest (+27 more)

### Community 69 - "nlu.py"
Cohesion: 0.23
Nodes (12): classify(), _head(), load_bank(), model_id(), Path, A3. Intent classification: multilingual sentence embedding + logistic head. The…, Intent plus slots. One call, one record in the trace., Returns intent, posterior, and the full ranking for the trace. The runner-up… (+4 more)

### Community 70 - "create_customer"
Cohesion: 0.11
Nodes (29): create_customer(), customer_summary(), find_by_mobile(), find_customer(), load_enrollment(), Connection, ndarray, The live embedding. Prefers the cache, falls back to decrypting the durable… (+21 more)

### Community 71 - "run_turn"
Cohesion: 0.10
Nodes (35): AuthOutcome, _authenticate(), _conversation_context(), detect_anomalies(), finalise(), scrub(), get_session(), Connection (+27 more)

### Community 72 - "test_persistence.py"
Cohesion: 0.10
Nodes (39): call_may_record(), ConsentError, Connection, PermissionError, Decrypt one recording. Compliance officers only, and always logged. The access…, Keep the clips an enrolment was built from, only on an explicit yes. Separate…, Raised when audio would be stored without a consented, noticed call., Both conditions, checked against the row rather than trusted. (+31 more)

### Community 73 - "db.py"
Cohesion: 0.21
Nodes (11): db_url(), One place decides where the data lives. Default is the SQLite file. Set…, _alembic_config(), engine(), migrate(), Database access. Two doors onto one SQLite file, deliberately: - `connect()`…, A SQLModel engine, one per URL, migrated on first use., Bring the database up to head. Idempotent, and run once per URL per process so… (+3 more)

### Community 74 - "test_speech_normaliser.py"
Cohesion: 0.09
Nodes (31): normalise_for_speech(), _money(), A reference code, letter by letter and digit by digit. IFSC codes, cheque…, Rewrite the things a synthesiser gets wrong, before it sees them. Most "wrong…, spell_code(), assert_devanagari(), Guard against a romanised Hindi or Marathi reply reaching the voice. Raises…, parametrize (+23 more)

### Community 75 - "Depends"
Cohesion: 0.16
Nodes (24): agent_accept(), audio_turn(), call_end(), case_callback(), claim_handover(), enroll(), eval_record(), ledger_verify() (+16 more)

### Community 76 - "turn.py"
Cohesion: 0.15
Nodes (21): SIMULATED core banking. Registered as SIMULATED in capabilities.py, and the…, Customers, voice enrolments and caller identification, all persistent. The…, _iso(), log_access(), purge_call(), purge_expired(), datetime, Call recording: consent-gated, encrypted, retained, and auditable. Change… (+13 more)

### Community 77 - "trace.py"
Cohesion: 0.15
Nodes (14): Status for a component, used to stamp trace stages. Unknown means SIMULATED.…, status_of(), canonical_json(), digest(), _input_digest(), Any, datetime, ComplianceTrace: the spine. One trace per turn, threaded through every stage.… (+6 more)

### Community 78 - "metrics.py"
Cohesion: 0.15
Nodes (16): calibrate_delta(), _canonical(), eer(), locate_entity(), min_tdcf(), ndarray, A9. Evaluation metrics, all computed here rather than imported. The Levenshtein…, Normalise a surface form so that the spellings of one value agree. "fifty… (+8 more)

### Community 79 - "scripts"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

### Community 80 - "create_session"
Cohesion: 0.13
Nodes (20): create_session(), Open a call and record consent as its first ledger entry. A session now belongs…, R2 depends on this: before it, a session referenced a customer by a string that…, test_a_session_belongs_to_a_persistent_call(), fixture, The turn path itself still holds query audio in memory only. Recordings are a…, Regression. The slot parser once read a phone number as an amount, and a…, session() (+12 more)

### Community 81 - "e2e/conftest.py"
Cohesion: 0.21
Nodes (11): _free(), fixture, A real browser against a real stack, on its own ports and its own database. The…, stack(), _stop_group(), _wait(), Popen, shutil (+3 more)

### Community 82 - "verify"
Cohesion: 0.16
Nodes (27): Authoritative O(n) verification from genesis., Verify the chain and localise the first break. With checkpoints, work is done…, verify(), verify_linear(), corrupt(), fill(), parametrize, P1 acceptance: the ledger must be stable before anything writes into it. (+19 more)

### Community 83 - "capabilities.py"
Cohesion: 0.33
Nodes (6): Capability, BaseModel, The honesty registry: the single source of truth for what is real here. A panel…, The CLU's registry entry depends on runtime configuration, so it is recomputed…, refresh_clu(), pydantic

### Community 84 - "test_providers.py"
Cohesion: 0.15
Nodes (14): health_report(), The configured provider for this language, or the local stack. Selection is per…, _registry(), tts_for(), usage_report(), R5. Cloud speech providers, and the local stack underneath them. The property…, It has never been called. Listing it REAL because the code exists would be…, test_an_unknown_provider_name_does_not_crash_the_turn() (+6 more)

### Community 85 - "_KeyedProvider"
Cohesion: 0.18
Nodes (10): ElevenLabsTTS, _KeyedProvider, ProviderUnavailable, RuntimeError, Shared health logic: no key means unavailable, and says so plainly., Bulbul, recommended for Hindi, Marathi and Indian English. Not exercised…, Flash v2.5, an option for English where speed matters most. The vendor's 75 ms…, This provider cannot serve the request. The caller falls back. (+2 more)

### Community 87 - "pytest"
Cohesion: 0.33
Nodes (6): conn(), live(), fixture, An empty, migrated database. No customers, no accounts, no models., A seeded database plus the real models. Uses the project runtime, since the…, pytest

### Community 88 - "pipeline/providers.py"
Cohesion: 0.21
Nodes (6): Health, LocalSTT, R5. Speech providers behind one interface, with the local stack underneath. Two…, stt_for(), STTProvider, D32. Cloud speech providers sit on top of the local stack, never in place of it

### Community 89 - "call_interrupt"
Cohesion: 0.25
Nodes (8): A turn is already running and the caller asked not to supersede it., TurnInFlight, _call_error(), call_interrupt(), InterruptRequest, Stop speaking. Works in every state. `played_ms` and `played_chars` are how…, Exception, HTTPException

### Community 90 - "asr.py"
Cohesion: 0.24
Nodes (10): Transcribe the rendered audio. Skipped, and said to be skipped, when the audio…, run_asr(), _model(), model_id(), ndarray, faster-whisper on CPU, int8. Not fine-tuned on banking audio. The capability…, Returns text plus an honest confidence. Whisper does not emit a calibrated…, transcribe() (+2 more)

### Community 92 - "latency_from_traces"
Cohesion: 0.50
Nodes (3): latency_from_traces(), p50 and p95 per stage, straight off the trace timings., test_latency_percentiles()

### Community 93 - "text_turn"
Cohesion: 0.22
Nodes (9): _one_turn(), Run the body as the call's single active turn. Yields the cancel token and the…, The text fallback. Everything after the transcript is identical to the voice…, Audio in, partial transcript and reply out. Protocol, deliberately small:…, _record_metrics(), text_turn(), TextTurnRequest, ws_session() (+1 more)

### Community 94 - "RetrievedPassage"
Cohesion: 0.25
Nodes (8): _cite(), _per_lang(), pick(), Build the same sentence in all three languages from one callable., Spoken citation. The document title and version are said aloud; the identifier…, BaseModel, RetrievedPassage, Reply

### Community 95 - "TTSProvider"
Cohesion: 0.22
Nodes (5): LocalTTS, Kokoro, falling through to Piper. Always available, never leaves., Speak text. `stream` yields audio chunks so the first one can play before the…, Stop generating. For a socket provider this closes the socket, which is the…, TTSProvider

### Community 96 - "speak"
Cohesion: 0.29
Nodes (7): Synthesise through the configured provider, falling back on trouble. Three…, speak(), slow, The dashboard has to be able to tell the truth about what spoke., R4's win depends on this: the first phrase plays while the rest is still being…, test_speaking_falls_back_and_says_which_engine_answered(), test_the_local_stack_streams_phrase_by_phrase()

### Community 97 - "OpenAICompatibleProvider"
Cohesion: 0.33
Nodes (4): OpenAICompatibleProvider, Groq, OpenRouter, Together, vLLM, Gemini's compatibility endpoint. The…, test_hosted_provider_without_a_key_fails_cleanly(), test_the_api_key_never_appears_in_a_provider_reply()

### Community 98 - "Customer.tsx"
Cohesion: 0.33
Nodes (4): Customer, Trace, MIC_CONSTRAINTS, Msg

### Community 100 - "_clean"
Cohesion: 0.67
Nodes (3): reset_usage(), _clean(), fixture

### Community 105 - "init_db"
Cohesion: 0.47
Nodes (6): connect(), init_db(), Connection, Path, A raw connection with the pragmas applied., Migrate to head, then hand back a raw connection. Tests pass an explicit path…

### Community 106 - "listening_check.py"
Cohesion: 0.40
Nodes (5): hashlib, random, main(), R5. Render the before and after voices for a blind listening check. The change…, render()

### Community 107 - "session"
Cohesion: 0.40
Nodes (5): A SQLModel session that commits on success and rolls back on error., session(), srv(), answer(), D20. SQLModel and Alembic replace hand-written SQL DDL

### Community 108 - "NotWhitelisted"
Cohesion: 0.50
Nodes (4): NotWhitelisted, PermissionError, An action nobody has signed off. Refused rather than attempted., D36. Protective actions: one, and a written reason for each of the others

### Community 109 - "dev_history"
Cohesion: 0.67
Nodes (3): dev_history(), 1 - exp(-lam * n). Saturating, so a session with six anomalies is not treated…, test_dev_history_saturates()

## Ambiguous Edges - Review These
- `FastAPI` → `Frontend single-page app shell`  [AMBIGUOUS]
  frontend/index.html · relation: shares_data_with
- `Data residency trade-off` → `DPDP Act 2023 and DPDP Rules`  [AMBIGUOUS]
  docs/CLU.md · relation: conceptually_related_to
- `Intent sensitivity table` → `Obligation, purpose limitation`  [AMBIGUOUS]
  docs/COMPLIANCE_MAPPING.md · relation: conceptually_related_to

## Knowledge Gaps
- **95 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+90 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 672 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `FastAPI` and `Frontend single-page app shell`?**
  _Edge tagged AMBIGUOUS (relation: shares_data_with) - confidence is low._
- **What is the exact relationship between `Data residency trade-off` and `DPDP Act 2023 and DPDP Rules`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Intent sensitivity table` and `Obligation, purpose limitation`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `run_turn()` connect `run_turn` to `crypto.py`, `tts.py`, `MockCore`, `ComplianceTrace`, `append`, `test_scenarios.py`, `langid.py`, `test_clu.py`, `merge_with_baseline`, `ProviderReply`, `test_voice_style.py`, `risk_score`, `retrieval.py`, `test_risk.py`, `dialogue.py`, `fuse_confidence`, `needs_grounding`, `nlu.py`, `test_persistence.py`, `turn.py`, `create_session`, `asr.py`, `text_turn`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `Decision log` connect `Decision log` to `tts.py`, `test_metrics.py`, `create_customer`, `ComplianceTrace`, `test_persistence.py`, `db.py`, `test_speech_normaliser.py`, `session`, `NotWhitelisted`, `test_investment.py`, `test_call_state.py`, `pipeline/providers.py`, `risk_score`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `utcnow()` connect `turn.py` to `ledger.py`, `clu_harness.py`, `harness.py`, `seed_data.py`, `main.py`, `create_customer`, `MockCore`, `append`, `test_persistence.py`, `run_turn`, `Depends`, `test_scenarios.py`, `trace.py`, `create_session`, `speaker.py`, `test_call_state.py`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `MockCore` (e.g. with `add_payee()` and `block_card()`) actually correct?**
  _`MockCore` has 17 INFERRED edges - model-reasoned connections that need verification._