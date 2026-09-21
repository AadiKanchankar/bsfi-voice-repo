# Graph Report - Projectdemo  (2026-09-21)

## Corpus Check
- 105 files · ~83,235 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: (none) 5, .example 1, .css 1)

## Summary
- 1325 nodes · 2821 edges · 68 communities (66 shown, 2 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 178 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Capability registry and ledger core
- FastAPI endpoints and API surface
- Configuration and SQLite access
- Audio decoding and voice activity detection
- Prosody, pauses and speech synthesis
- Anti-spoofing LFCC and GMM baseline
- Mock core banking reads and writes
- Per-intent action handlers
- Turn orchestration and authentication
- PII redaction, Luhn and Verhoeff
- Architecture layers and stack choices
- Session lifecycle and the ten demo beats
- Code-switch language identification
- Indian-numbering speech text
- CLU prompt and providers
- Language and intent algorithms
- Investment advice boundary
- HTTP contract and role matrix tests
- Tamper-evident ledger and compliance layer
- CLU routing and call decisions
- Sentence embeddings and intent head
- CLU safety floor and merge
- PII, consent and DPDP obligations
- Risk ladder, retrieval floor and the gate
- CLU output parsing and failure handling
- Rule-based slot extraction
- Deposit and savings account policy
- CLU result schema validation
- Speaker verification and the demo script
- Frontend API client and components
- TypeScript build configuration
- Risk scoring terms
- Evaluation metrics and honest limitations
- Card, cheque and account intents
- Evaluation harness
- Fees, charges and transaction limits
- Clu Harness
- Metric implementations and calibration
- Retrieval indexing and MMR
- Home loan and lending policy
- Investment products and SEBI boundary
- Demo()
- Test Metrics
- Ratchet Guards
- Traceviewx
- Assign Tier()
- Package.Json
- .Available()
- Mainx
- Asr
- Add()
- Test Risk
- Parametrize
- Path
- Intent: Agent Request
- .Available()
- .Errors()
- Branch Timings
- Runs Retrieval()
- Video Kyc Onboarding
- Vite
- .Available()
- Pct()
- Ratchet Should Raise()
- Recompute From Components()
- React
- Dev
- Cryptography

## God Nodes (most connected - your core abstractions)
1. `MockCore` - 44 edges
2. `run_turn()` - 37 edges
3. `ComplianceTrace` - 35 edges
4. `utcnow()` - 29 edges
5. `verify()` - 23 edges
6. `CLUResult` - 22 edges
7. `require()` - 21 edges
8. `conn()` - 20 edges
9. `Compliance-Aware Multilingual Voice Assistant for BFSI` - 19 edges
10. `Ten-beat demo script` - 19 edges

## Surprising Connections (you probably didn't know these)
- `api container service` --references--> `FastAPI`  [INFERRED]
  docker-compose.yml → backend/requirements.txt
- `seed_presenter()` --uses--> `MockCore`  [INFERRED]
  scripts/seed_data.py → backend/app/banking/mock_core.py
- `graphify query workflow` --conceptually_related_to--> `Compliance-Aware Multilingual Voice Assistant for BFSI`  [INFERRED]
  CLAUDE.md → README.md
- `Compliance-Aware Multilingual Voice Assistant for BFSI` --references--> `Frontend single-page app shell`  [INFERRED]
  README.md → frontend/index.html
- `Auditability is architectural` --rationale_for--> `Cascaded voice pipeline`  [INFERRED]
  README.md → docs/ARCHITECTURE.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The four architectural layers** — docs_architecture_voice_and_ai_layer, docs_architecture_integration_middleware_layer, docs_architecture_compliance_layer, docs_architecture_dashboard_layer, docs_architecture_four_layer_architecture [EXTRACTED 1.00]
- **Stages of one audited turn** — docs_algorithms_code_switch_language_identification, docs_algorithms_intent_classification, docs_algorithms_retrieval_grounding, docs_algorithms_confidence_fusion, docs_algorithms_speaker_verification, docs_algorithms_risk_scoring, docs_algorithms_automation_gate, docs_algorithms_pii_redaction, docs_algorithms_tamper_evident_ledger [EXTRACTED 1.00]
- **Enforced risk-tier safety properties** — docs_algorithms_hard_tier_override, docs_algorithms_session_tier_ratchet, docs_algorithms_ratchet_guards, docs_algorithms_min_tier_by_intent, docs_algorithms_four_tier_ladder, docs_algorithms_automation_gate [EXTRACTED 1.00]
- **Refusal and Human Handoff Path** — data_seed_intent_bank_out_of_scope, data_seed_intent_bank_investment_advice, data_seed_intent_bank_agent_request, data_policy_kb_investment_advice_policy_investment_advice_refusal, data_policy_kb_fraud_reporting_fraud_report_handling, data_policy_kb_investment_advice_policy_suitability_and_risk_profiling [INFERRED 0.85]
- **Compromised Card Response Flow** — data_seed_intent_bank_block_card, data_seed_intent_bank_fraud_report, data_policy_kb_card_blocking_card_block, data_policy_kb_card_blocking_unauthorised_transaction_liability, data_policy_kb_card_blocking_replacement_card, data_policy_kb_fraud_reporting_shadow_credit, data_policy_kb_fraud_reporting_cybercrime_portal_reference [INFERRED 0.85]
- **Home Loan Rate Policy Version Chain (POL-HL-001)** — data_policy_kb_home_loan_rates_v1_pol_hl_001, data_policy_kb_home_loan_rates_v2_pol_hl_001, data_policy_kb_home_loan_rates_v1_interest_rate_slabs, data_policy_kb_home_loan_rates_v2_interest_rate_slabs, data_policy_kb_home_loan_rates_v1_processing_fee, data_policy_kb_home_loan_rates_v2_processing_fee, data_policy_kb_loan_eligibility_home_loan_eligibility [EXTRACTED 1.00]

## Communities (68 total, 2 thin omitted)

### Community 0 - "Capability registry and ledger core"
Cohesion: 0.05
Nodes (72): Capability, BaseModel, The honesty registry: the single source of truth for what is real here. A panel…, Status for a component, used to stamp trace stages. Unknown means SIMULATED.…, The CLU's registry entry depends on runtime configuration, so it is recomputed…, refresh_clu(), registry_dict(), status_of() (+64 more)

### Community 1 - "FastAPI endpoints and API surface"
Cohesion: 0.06
Nodes (73): asyncio, audio_turn(), capabilities(), claim_handover(), conn(), ConsentRequest, create_consent(), customers() (+65 more)

### Community 2 - "Configuration and SQLite access"
Cohesion: 0.05
Nodes (57): argparse, _load_calibration(), _load_dotenv(), Every tunable number in the system lives here. Rule for this file: if a value…, Read .env before anything else looks at the environment. The CLU provider key…, Overlay measured values written by `make eval` / scripts/calibrate.py. Keeps…, connect(), init_db() (+49 more)

### Community 3 - "Audio decoding and voice activity detection"
Cohesion: 0.06
Nodes (53): decode(), _decode_container(), duration_s(), _is_container(), ndarray, Audio helpers shared by VAD, ASR, speaker verification and anti-spoofing.…, Bytes to float32 mono at SAMPLE_RATE. Handles WAV directly, anything else…, Decode a compressed container with PyAV, resampling to mono 16 kHz. PyAV ships… (+45 more)

### Community 4 - "Prosody, pauses and speech synthesis"
Cohesion: 0.10
Nodes (39): assemble(), breath(), demo(), ndarray, Random, Making synthesised speech breathe. A neural voice handed a whole paragraph…, Synthesise phrase by phrase and join with pauses. `synth(phrase, speed) ->…, Text to (phrase, pause after it in seconds). (+31 more)

### Community 5 - "Anti-spoofing LFCC and GMM baseline"
Cohesion: 0.10
Nodes (31): run_biometrics(), AntiSpoofScorer, _deltas(), lfcc(), LfccGmmScorer, _linear_filterbank(), model_id(), ndarray (+23 more)

### Community 6 - "Mock core banking reads and writes"
Cohesion: 0.07
Nodes (14): MockCore, Connection, Current value, cost and unrealised gain. Facts only: nothing here is a view on…, Match on the words of the question, not the whole sentence. A LIKE pattern…, core(), fixture, The mock core banking layer. SIMULATED, but its lookups still have to work., A LIKE pattern built from the entire utterance matches nothing, which silently… (+6 more)

### Community 7 - "Per-intent action handlers"
Cohesion: 0.13
Nodes (32): add_payee(), _amt(), answer_from_policy(), block_card(), branch_ifsc(), cheque_status(), _cite(), escalate() (+24 more)

### Community 8 - "Turn orchestration and authentication"
Cohesion: 0.12
Nodes (33): SIMULATED core banking. Registered as SIMULATED in capabilities.py, and the…, AuthOutcome, utcnow(), _authenticate(), build_handover_packet(), _conversation_context(), detect_anomalies(), finalise() (+25 more)

### Community 9 - "PII redaction, Luhn and Verhoeff"
Cohesion: 0.10
Nodes (32): demo(), find_spoken_digit_runs(), luhn_check(), luhn_checkdigit(), A7. PII detection and tokenisation, run before anything touches disk. Two…, Returns (char_start, char_end, digits) for runs of >= MIN_SPOKEN_DIGITS…, Replace every detected identifier with a stable token. `counters` and `seen`…, Mod-10 checksum. Double every second digit from the right, subtract 9 from any… (+24 more)

### Community 10 - "Architecture layers and stack choices"
Cohesion: 0.08
Nodes (33): CPU-only dependency constraint, FastAPI, faster-whisper, kokoro-onnx, piper-tts, scikit-learn, sentence-transformers, Spoken digit recovery (+25 more)

### Community 11 - "Session lifecycle and the ten demo beats"
Cohesion: 0.10
Nodes (30): create_session(), Run a voice check and store the outcome on the session. This is the only thing…, Open a session and record consent as the first ledger entry of the call., record_verification(), ask(), live(), fixture, P2 acceptance: all ten demo beats, in text mode, as one file. This is the… (+22 more)

### Community 12 - "Code-switch language identification"
Cohesion: 0.11
Nodes (28): code_mix_index(), demo(), identify(), _is_devanagari(), _is_perso_arabic(), merge_spans(), A1. Code-switch-aware language identification. Per-word language evidence is…, Best language path under the switch penalty. Returns one label per word. (+20 more)

### Community 13 - "Indian-numbering speech text"
Cohesion: 0.12
Nodes (24): line(), readback_summary(), demo(), _en_below_thousand(), _hi_below_thousand(), _mr_below_thousand(), Turning values into words a synthesiser can say naturally. Piper is an espeak-…, An amount in Indian numbering, as words. 206465.68 in English becomes 'two lakh… (+16 more)

### Community 14 - "CLU prompt and providers"
Cohesion: 0.12
Nodes (18): _coordinates_two_asks(), Contextual Language Understanding. What it is for: real speech is code-mixed,…, A coordinator with real content on both sides. Bare "and" is too common to…, build_user_prompt(), example_messages(), The prompt, versioned and kept small. PROMPT_VERSION goes into every trace and…, The turn, plus a bounded slice of what came before it., Two shots, for the two things a small model gets wrong without them. (+10 more)

### Community 15 - "Language and intent algorithms"
Cohesion: 0.13
Nodes (25): Indian-numbering amount parsing, Code-mix index, A1 code-switch-aware language identification, A2 geometric confidence fusion, Seed intent utterance bank, A3 intent classification, Rule-based slot extraction, Script and lexicon posterior prior (+17 more)

### Community 16 - "Investment advice boundary"
Cohesion: 0.14
Nodes (20): investment_advice(), investment_info(), Facts about a customer's own investments, or about a product. Everything here…, Refuse, explain, and hand to someone licensed to answer. Not a hedged answer. A…, blank_trace(), core(), fixture, parametrize (+12 more)

### Community 17 - "HTTP contract and role matrix tests"
Cohesion: 0.12
Nodes (18): client(), fixture, parametrize, Section 8. The HTTP contract and the authorisation boundary on it. These tests…, A throwaway database per test. main.DB_PATH is patched rather than main.CONN,…, The single most important cell in the role matrix., test_compliance_officer_can_export_the_ledger(), test_compliance_officer_cannot_submit_a_turn() (+10 more)

### Community 18 - "Tamper-evident ledger and compliance layer"
Cohesion: 0.15
Nodes (22): graphify skill directive, graphify query workflow, Ledger checkpoints, Three independent ledger checks, A8 tamper-evident hash-chain ledger, Tamper localisation, Layer 3, compliance, ComplianceTrace (+14 more)

### Community 19 - "CLU routing and call decisions"
Cohesion: 0.15
Nodes (19): enabled(), Whether this turn is worth a model call. Most turns are not. A confident,…, should_call(), get_provider(), provider_names(), The contextual language layer. Most of this file is about what the CLU is NOT…, Explicitly disabled, not "whatever .env happens to say": this test used to…, A single-label head cannot represent the second ask at ANY confidence, so… (+11 more)

### Community 20 - "Sentence embeddings and intent head"
Cohesion: 0.14
Nodes (19): cosine(), encode(), get_model(), ndarray, One sentence-transformer, loaded once, shared by the NLU head and retrieval.…, Prefer the pre-downloaded local copy so a demo launch never touches the…, Cosine similarity of a single vector against a matrix of row vectors., classify() (+11 more)

### Community 21 - "CLU safety floor and merge"
Cohesion: 0.14
Nodes (19): CLUOutcome, merge_with_baseline(), Combine the two readings under the safety floor. The rule: the CLU may raise…, Everything the trace needs to explain what the language layer did., outcome(), parametrize, Rule-based extraction is auditable; model output is not., The single most important test in this file. (+11 more)

### Community 22 - "PII, consent and DPDP obligations"
Cohesion: 0.15
Nodes (20): PyJWT, Demo environment secrets, Consent withdrawal purge, Intent sensitivity table, Luhn mod-10 check, A7 PII redaction before persistence, Per-session token map and AES-256-GCM vault, Verhoeff dihedral check (+12 more)

### Community 23 - "Risk ladder, retrieval floor and the gate"
Cohesion: 0.16
Nodes (20): Silero VAD, Log-scaled amount normalisation, Saturating anomaly deviation term, The automation gate, Lowest floor meeting a precision constraint, Four-tier risk ladder, Per-intent minimum tier, Maximal marginal relevance (+12 more)

### Community 24 - "CLU output parsing and failure handling"
Cohesion: 0.15
Nodes (13): _extract_json(), Models fence their JSON, prefix it, or append an apology. Take the first…, The one entry point. Everything above this is provider-agnostic. Never raises.…, understand_turn(), ProviderReply, What a provider hands back, before schema validation., test_a_provider_that_raises_does_not_break_the_turn(), test_conversation_context_is_bounded() (+5 more)

### Community 25 - "Rule-based slot extraction"
Cohesion: 0.19
Nodes (16): demo(), extract(), parse_amount(), A3, second half. Slot extraction by rule, not by model. Rules are auditable,…, All slots for one utterance. Only non-empty slots are returned, so the trace…, Digits first, then word numbers. Returns None when no amount is present., test_phone_number_is_never_parsed_as_an_amount(), parametrize (+8 more)

### Community 26 - "Deposit and savings account policy"
Cohesion: 0.14
Nodes (18): Basic Savings Bank Deposit Account, Deposit Account Nomination, POL-ACC-013 Account Opening and Types v1.6, Salary Account, Nigdi Branch (DEMO0001234), POL-FD-009 Fixed Deposit Schemes and Rates v3.2, Premature Withdrawal Penalty, Senior Citizen Rate Benefit (+10 more)

### Community 27 - "CLU result schema validation"
Cohesion: 0.15
Nodes (11): CLUResult, BaseModel, Structured understanding of one turn., test_confidence_is_clamped(), test_free_text_fields_are_bounded(), test_sub_intent_cannot_duplicate_the_primary(), test_two_languages_implies_code_mixed(), test_unknown_intent_is_rejected() (+3 more)

### Community 28 - "Speaker verification and the demo script"
Cohesion: 0.17
Nodes (17): SpeechBrain, Anti-spoofing BASELINE countermeasure, ECAPA-TDNN enrolment, LFCC and GMM log-likelihood ratio, A6 speaker verification, Verification expiry and the SIMULATED fallback, Conflict C3, AASIST downgraded to a baseline, Demo persona CUST9001 (+9 more)

### Community 29 - "Frontend API client and components"
Cohesion: 0.21
Nodes (13): api, AuthOutcome, Capability, getToken(), LanguageSpan, req(), RetrievedPassage, StageRecord (+5 more)

### Community 30 - "TypeScript build configuration"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+8 more)

### Community 31 - "Risk scoring terms"
Cohesion: 0.16
Nodes (15): dev_history(), norm_amount(), A2 and A5. Confidence fusion, risk scoring, tier assignment, and the policy…, min(1, log1p(a) / log1p(A_max)). Log scale because the step from 1,000 to…, 1 - exp(-lam * n). Saturating, so a session with six anomalies is not treated…, Whether knowing who is speaking matters for this intent. Public information…, R = w1*sens + w2*norm(amount) + w3*(1 - s_verify) + w4*dev(history). Returns…, requires_identity() (+7 more)

### Community 32 - "Evaluation metrics and honest limitations"
Cohesion: 0.23
Nodes (16): api container service, Measured calibration file, Entity-level error rate, A9 evaluation metrics, Hand-labelled evaluation set, Normalised minimum t-DCF, Word error rate with Levenshtein alignment, Anti-spoof measurement compares two synthesis conditions (+8 more)

### Community 33 - "Card, cheque and account intents"
Cohesion: 0.21
Nodes (15): Card Block, POL-CRD-002 Debit and Credit Card Blocking v2.3, Unauthorised Transaction Liability Ladder, Cheque Truncation System Clearing, POL-CHQ-003 Cheque Collection and Clearing v1.4, Stop Payment Instruction, Fixed Deposit Interest Rate Slabs, Savings Interest Rate Slabs (+7 more)

### Community 34 - "Evaluation harness"
Cohesion: 0.21
Nodes (12): load_set(), `make eval` runs this. It regenerates every number in docs/RESULTS.md from…, Dominant-language accuracy plus the CMI distribution. Code-mixed utterances are…, Calibrate the refusal floor on the split that actually matters. The negative…, render_markdown(), _row(), run_all(), run_langid() (+4 more)

### Community 35 - "Fees, charges and transaction limits"
Cohesion: 0.20
Nodes (14): IFSC Code, Replacement Card Issuance, Cheque Return Charges, ATM Transaction Charges, Debit Card Charges, Fund Transfer Charges, POL-FEE-007 Schedule of Fees and Charges v4.1, Daily ATM and POS Limits (+6 more)

### Community 36 - "Clu Harness"
Cohesion: 0.24
Nodes (12): _delta(), _entities_match(), load_cases(), Baseline against baseline-plus-CLU, on the cases the baseline is expected to…, Every expected entity present and equal. Extra entities are allowed: over-…, The deterministic classifier alone, exactly as the frozen snapshot., Deterministic classifier, then the CLU on the turns the router picks. `pace_s`…, render() (+4 more)

### Community 37 - "Metric implementations and calibration"
Cohesion: 0.21
Nodes (12): calibrate_delta(), eer(), min_tdcf(), ndarray, A9. Evaluation metrics, all computed here rather than imported. The Levenshtein…, Pick the similarity floor, and report what the choice costs. Two candidates,…, Normalised minimum tandem detection cost function. Follows the ASVspoof 2019…, _scores_at() (+4 more)

### Community 38 - "Retrieval indexing and MMR"
Cohesion: 0.22
Nodes (12): build_index(), chunk_document(), _index(), mmr_select(), parse_front_matter(), ndarray, Path, A4. Retrieval grounding with an explicit refusal path. The refusal path is the… (+4 more)

### Community 39 - "Home loan and lending policy"
Cohesion: 0.23
Nodes (13): Home Loan Rate Slabs (FY 2025-26), Loan to Value Ratio Cap, POL-HL-001 Home Loan Interest Rates v1.0 (superseded), Home Loan Processing Fee (0.35 percent), Home Loan Rate Slabs (from 1 April 2026), POL-HL-001 Home Loan Interest Rates v1.1 (current), Home Loan Processing Fee (0.30 percent), Women Applicant Concession (5 bps) (+5 more)

### Community 40 - "Investment products and SEBI boundary"
Cohesion: 0.27
Nodes (13): Automated Investment Advice Refusal, Past Performance Disclaimer, POL-INV-016 Investment Advice and the Limits of Automated Service v1.0, Registered Investment Adviser, SEBI (Investment Advisers) Regulations 2013, Suitability and Risk Profiling, Demat Account Charges and Brokerage, POL-INV-015 Investment Services, Demat and Mutual Funds v1.0 (+5 more)

### Community 41 - "Demo()"
Cohesion: 0.18
Nodes (12): _canonical(), demo(), entity_error_rate(), locate_entity(), Normalise a surface form so that the spellings of one value agree. "fifty…, Find the token span in the reference that realises this entity. Tried as…, EER_s = (1/|E|) * sum 1[e_hat != e], per entity type and overall. Each…, fifty thousand" heard as "50,000" is correct, not an error. Before this was… (+4 more)

### Community 42 - "Test Metrics"
Cohesion: 0.23
Nodes (11): corpus_wer(), normalize_tokens(), WER = (S + D + I) / N., Pooled WER over a corpus, which is the correct aggregate. Averaging per-…, wer(), A9. The metrics have to be right before any number they produce is quoted., Averaging per-utterance WER over-weights short utterances., test_corpus_wer_is_pooled_not_averaged() (+3 more)

### Community 43 - "Ratchet Guards"
Cohesion: 0.24
Nodes (12): Hard tier 3 override, Ratchet guards, Session tier ratchet, Investment advice boundary, NON_RATCHETING_TIER3 carve-out, SEBI Investment Advisers Regulations 2013, Four defects found by a recorded session, Downgrade carve-out for unconfident hard-handover readings (+4 more)

### Community 44 - "Traceviewx"
Cohesion: 0.26
Nodes (8): AuthPanel(), LanguagePanel(), num(), pct(), RetrievalPanel(), RiskPanel(), StageTimeline(), TraceView()

### Community 45 - "Assign Tier()"
Cohesion: 0.18
Nodes (11): assign_tier(), Tier is the maximum of three things: what the score says, what the intent's own…, tier_from_score(), test_advice_can_never_be_automated_whatever_the_score(), Without the public-intent rule every unverified turn scores at least 0.25 = t1…, One misheard turn used to make the assistant refuse to quote its own published…, test_account_intents_still_pay_the_verification_term(), test_public_information_can_reach_tier_zero() (+3 more)

### Community 46 - "Package.Json"
Cohesion: 0.20
Nodes (9): name, private, type, version, @types/react, @types/react-dom, typescript, vite (+1 more)

### Community 47 - ".Available()"
Cohesion: 0.20
Nodes (5): MockProvider, NullProvider, Offline stand-in with no model behind it. It exists so the plumbing, the…, test_hosted_provider_declares_that_data_leaves_the_machine(), test_mock_provider_reads_a_compound_code_mixed_request()

### Community 48 - "Mainx"
Cohesion: 0.22
Nodes (6): Customer, Compliance(), Msg, frontend_src_styles, react-dom, react-router-dom

### Community 49 - "Asr"
Cohesion: 0.31
Nodes (8): Transcribe the rendered audio. Skipped, and said to be skipped, when the audio…, run_asr(), _model(), model_id(), ndarray, faster-whisper on CPU, int8. Not fine-tuned on banking audio. The capability…, Returns text plus an honest confidence. Whisper does not emit a calibrated…, transcribe()

### Community 50 - "Add()"
Cohesion: 0.22
Nodes (8): ceiling_for(), gate(), The R below which a turn at this tier may be automated. Tier 3 has none., Automate only when every condition holds. Otherwise refuse or escalate. The…, tau_for(), test_gate_refuses_when_ungrounded(), test_gate_reports_the_first_failing_condition(), test_tier3_tau_is_unreachable()

### Community 51 - "Test Risk"
Cohesion: 0.25
Nodes (7): fuse_confidence(), c_final = c_asr^alpha * c_intent^beta * c_retr^gamma. Geometric, not…, A2 and A5. Deterministic, so exact values, plus the property test the paper…, An average would let a confident intent hide a terrible transcript., test_fusion_exponents_sum_to_one(), test_fusion_is_geometric_and_vetoable(), random

### Community 52 - "Parametrize"
Cohesion: 0.25
Nodes (9): ratchet_applies(), Whether the session floor binds this turn. Public-information intents are…, parametrize, A confident identity must not be able to skip the read-back on an action that…, A scoring bug must never be able to automate a fraud report., test_account_intents_are_not_ratchet_exempt(), test_hard_override_beats_any_score(), test_intent_floor_holds_even_with_perfect_verification() (+1 more)

### Community 53 - "Path"
Cohesion: 0.28
Nodes (9): model_id(), load_bank(), Path, train(), _is_current(), Returns passages above the floor, the max score achieved, and the floor. The…, search(), passage() (+1 more)

### Community 54 - "Intent: Agent Request"
Cohesion: 0.33
Nodes (9): National Cybercrime Reporting Portal Reference, Human-Only Fraud Report Handling, POL-FRD-012 Fraud Reporting and Customer Protection v2.5, Shadow Credit Pending Investigation, Reserve Bank Integrated Ombudsman Scheme, Nodal Officer (Regional Office), POL-GRV-005 Grievance Redressal and Escalation v2.0, Principal Nodal Officer (Head Office) (+1 more)

### Community 55 - ".Available()"
Cohesion: 0.33
Nodes (4): OpenAICompatibleProvider, Groq, OpenRouter, Together, vLLM, Gemini's compatibility endpoint. The…, test_hosted_provider_without_a_key_fails_cleanly(), test_the_api_key_never_appears_in_a_provider_reply()

### Community 56 - ".Errors()"
Cohesion: 0.29
Nodes (4): align(), Alignment, Hypothesis token indices covering reference tokens [start, end). Insertions…, Levenshtein alignment with backpointers. O(|ref| * |hyp|).

### Community 57 - "Branch Timings"
Cohesion: 0.33
Nodes (7): Andheri East Branch (DEMO0002101), Branch Timings, Hadapsar Branch (DEMO0001236), Kothrud Branch (DEMO0001235), Nashik Road Branch (DEMO0003301), POL-BRN-006 Branch Network and IFSC Codes v1.2, Intent: branch_ifsc

### Community 58 - "Runs Retrieval()"
Cohesion: 0.33
Nodes (6): needs_grounding(), Whether to search the policy knowledge base for this intent., Whether an empty retrieval result must block the answer. Stricter than…, runs_retrieval(), A cheque status comes from the cheque table, so an empty policy search must not…, test_retrieval_and_grounding_are_different_questions()

### Community 59 - "Video Kyc Onboarding"
Cohesion: 0.40
Nodes (6): Video KYC Onboarding, Demat and Trading Account, Incomplete KYC Account Restrictions, Officially Valid Document, Periodic KYC Updation by Risk Tier, POL-KYC-004 Know Your Customer Requirements v3.0

### Community 60 - "Vite"
Cohesion: 0.33
Nodes (6): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react

### Community 62 - "Pct()"
Cohesion: 0.50
Nodes (3): latency_from_traces(), p50 and p95 per stage, straight off the trace timings., test_latency_percentiles()

### Community 63 - "Ratchet Should Raise()"
Cohesion: 0.50
Nodes (4): ratchet_should_raise(), Whether THIS turn is allowed to raise the session floor. A turn escalates on…, A garbled transcript should escalate the turn and leave the call usable., test_a_low_confidence_escalation_does_not_pin_the_session()

### Community 64 - "Recompute From Components()"
Cohesion: 0.50
Nodes (4): Independent recomputation used by the property test. Reads only what the trace…, recompute_from_components(), The property the paper claims: a reviewer can recompute the decision from the…, test_recompute_from_components_matches_stored_score()

### Community 65 - "React"
Cohesion: 0.50
Nodes (4): dependencies, react, react-dom, react-router-dom

### Community 66 - "Dev"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

## Ambiguous Edges - Review These
- `FastAPI` → `Frontend single-page app shell`  [AMBIGUOUS]
  frontend/index.html · relation: shares_data_with
- `Intent sensitivity table` → `Obligation, purpose limitation`  [AMBIGUOUS]
  docs/COMPLIANCE_MAPPING.md · relation: conceptually_related_to
- `Data residency trade-off` → `DPDP Act 2023 and DPDP Rules`  [AMBIGUOUS]
  docs/CLU.md · relation: conceptually_related_to

## Knowledge Gaps
- **60 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+55 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 388 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `FastAPI` and `Frontend single-page app shell`?**
  _Edge tagged AMBIGUOUS (relation: shares_data_with) - confidence is low._
- **What is the exact relationship between `Intent sensitivity table` and `Obligation, purpose limitation`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Data residency trade-off` and `DPDP Act 2023 and DPDP Rules`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `run_turn()` connect `Turn orchestration and authentication` to `FastAPI endpoints and API surface`, `Audio decoding and voice activity detection`, `Mock core banking reads and writes`, `Per-intent action handlers`, `Session lifecycle and the ten demo beats`, `Code-switch language identification`, `Assign Tier()`, `Asr`, `Add()`, `CLU routing and call decisions`, `Test Risk`, `CLU safety floor and merge`, `Sentence embeddings and intent head`, `Path`, `CLU output parsing and failure handling`, `Runs Retrieval()`, `Risk scoring terms`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `MockCore` connect `Mock core banking reads and writes` to `Investment advice boundary`, `Turn orchestration and authentication`, `Configuration and SQLite access`, `Per-intent action handlers`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `utcnow()` connect `Turn orchestration and authentication` to `Capability registry and ledger core`, `FastAPI endpoints and API surface`, `Evaluation harness`, `Configuration and SQLite access`, `Clu Harness`, `Anti-spoofing LFCC and GMM baseline`, `Mock core banking reads and writes`, `Session lifecycle and the ten demo beats`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `MockCore` (e.g. with `add_payee()` and `block_card()`) actually correct?**
  _`MockCore` has 15 INFERRED edges - model-reasoned connections that need verification._