# Architecture

This document restates the design in my own words, so that a mismatch between
what the paper says, what the synopsis says and what the code does is visible
rather than buried. Section 5 lists every conflict I found between the build
prompt and the two source documents, with the resolution I applied and the
reason. Those are the points to review first.

## 1. The one idea

The system is a cascaded voice pipeline for banking customer service in
English, Hindi and Marathi, including utterances that switch between them
mid-sentence. The interesting property is not that it talks. It is that every
stage of every turn leaves an inspectable record, and that a compliance officer
can reconstruct any decision from those records alone, months later, without
access to the process that made it.

A cascaded pipeline is slower than an end-to-end speech-to-speech model and is
chosen anyway, because each stage emits a discrete artefact a reviewer can
read: a timestamped transcript, a language tag, an intent with a posterior, a
retrieved policy passage with its version, an authentication outcome, a risk
score with every term visible, a decision and the action taken. An end-to-end
model emits audio and nothing else. The synopsis makes this argument and the
implementation takes it literally.

## 2. Layers

Four layers, matching Figure 1 of the synopsis. The paper's Section III
describes three; the compliance layer is the fourth and is named in the paper's
abstract ("secure middleware and a compliance layer"). See section 5, conflict
C1.

```
Layer 1  Voice and AI            VAD, ASR, language identification, NLU,
         (teal)                  dialogue policy, TTS
Layer 2  Integration middleware  core banking adapter, action dispatch, RBAC,
         (amber)                 session state, escalation routing
Layer 3  Compliance              ComplianceTrace, PII redaction, encryption at
         (red)                   rest, consent and retention, hash-chained ledger
Layer 4  Dashboard               customer console, compliance dashboard, agent
                                 queue, capability legend, ledger verification
```

The compliance layer is not a sink that the other layers report into after the
fact. It owns the object that the other layers write through. That distinction
is the whole claim.

## 3. One turn, end to end

```
consent (once per session, first ledger record)
   |
   v
audio ---> VAD ---> ASR ---------> transcript, c_asr
                      |            (text fallback enters here, identically)
                      v
                 language ID  ---> spans, code-mix index, dominant language
                      |
                      v
                    NLU      ---> intent, c_intent, slots (rule based)
                      |
                      v
                 retrieval   ---> passages above delta with doc_id and version,
                      |           or nothing, which means refuse
                      v
              confidence fusion --> c_final = c_asr^a * c_intent^b * c_retr^g
                      |
                      v
                 anomalies   ---> new device, unusual hour, first-ever payee,
                      |           rapid repeats
                      v
              authentication ---> ECAPA cosine x anti-spoof score = s_verify
                      |
                      v
                 risk score  ---> R, tier, hard overrides, session ratchet
                      |
                      v
                  the gate   ---> automated | refused | escalated
                      |
                      v
                   action    ---> mock core banking, or refusal, or handover
                      |
                      v
                    reply    ---> template text, Piper speech in the dominant language
                      |
                      v
              PII redaction  ---> tokens out, raw values into the encrypted vault
                      |
                      v
              persist trace  ---> traces table (redacted)
                      |
                      v
              ledger append  ---> SHA-256 chain + HMAC signature
```

Nothing writes to disk before the redaction step. Raw audio is held in memory
only for as long as transcription needs it, and is dropped immediately after.

## 4. ComplianceTrace

One object per turn, created at the start and threaded through every stage.
Stages append; nothing overwrites. The enforced rule is that no stage may
influence a decision with a number that is not in the trace, which is checked
by `tests/test_risk.py::test_recompute_from_components_matches_stored_score`:
the risk score is recomputed from `risk_components` alone and must equal the
stored `risk_score` exactly. Risk components are therefore stored unrounded;
rounding for display is the dashboard's job.

Each stage record carries the SHA-256 digest of its input rather than the input
itself, its duration, the model identifier, and its capability status from the
honesty registry. A `SIMULATED` stage is marked as such on screen.

## 5. Conflicts between the build prompt and the source documents

These are the points where the prompt and the two source documents disagree.
Each one is flagged here rather than resolved silently. The resolutions applied
are marked, and any of them can be reversed.

**C1. Three layers or four.** The prompt (section 13) asks for a "four-layer
architecture, matching Figure 1 of the synopsis". The paper's Section III
describes three layers: Core Voice and AI, Integration Middleware, and Admin
Dashboard. The synopsis abstract separately names "secure middleware and a
compliance layer". *Resolution applied:* four layers, with compliance split out
from middleware, since that split is what the whole project argues for. If
Figure 1 of the synopsis genuinely shows three boxes, the diagram script in
`scripts/diagrams/generate.py` needs one line changed.

**C2. Five languages or three.** The synopsis objective 1 commits to "at least
five Indian languages". The prompt scopes the demo to English, Hindi and
Marathi. *Resolution applied:* three, as the prompt says. The language list is
`config.LANGUAGES` and the Viterbi tagger is written for an arbitrary state
set, so adding languages is a config change plus a lexicon, not a rewrite. This
gap should be stated in the review, not hidden.

**C3. Anti-spoofing.** Synopsis and paper both name an AASIST-style
countermeasure. The prompt correctly downgrades this to an LFCC and GMM
baseline and requires it to be labelled `BASELINE`. *Resolution applied:* as
the prompt says, and the label appears in the registry, in the trace, on the
dashboard and in RESULTS.md.

**C4. Fine-tuned ASR.** The synopsis describes Whisper "fine-tuned on a banking
corpus". No fine-tuning happens in this build. *Resolution applied:* the
capability note says so, and RESULTS.md frames the measured entity-level error
rate as the baseline a fine-tuned model must beat.

**C5. Blockchain audit trail.** The paper retains the base system's
blockchain-based logging. The synopsis already argues for "simpler,
cryptographically signed logging" instead. The prompt specifies a hash chain.
*Resolution applied:* hash chain with HMAC signatures. The paper's Section IV
comparison table should be updated to match, because as written it claims
blockchain.

**C6. A likely typo in the paper.** Paper Section III.D reads: "It ranks the
query and decides whether the query is simple enough to be automated without
human intervention, if yes the query is routed to the humans." The logic is
inverted; it should read "if no". Worth fixing before the camera-ready version.

**C7. Two different things are both called EER.** The synopsis uses `EER_s` for
the entity-level error rate and EER for the equal error rate of speaker
verification. The prompt's section A9 uses "EER" for both. *Resolution
applied:* the code calls them `entity_error_rate` and `eer` and never
abbreviates the first one. RESULTS.md spells both out.

**C8. Tamper localisation complexity.** The prompt states localisation is
`O(log n) + O(k)` via binary search over checkpoints. That holds when the
corruption propagates to the end of the chain, which is the case when an
attacker rewrites hashes forward. A single edited payload that leaves every
stored hash untouched breaks nothing downstream, so no checkpoint anchor
disagrees and the search has to walk the anchors in order. *Resolution
applied:* implemented as specified with an in-order fallback, so the answer is
always correct; both cases are asserted in `tests/test_ledger.py` and the true
cost is stated in ALGORITHMS.md. Genuine `O(log n)` inclusion proofs for a
single record need the Merkle upgrade listed in the stretch goals.

**C9. The risk formula as specified makes tier 0 unreachable, and lets a
verified caller skip the read-back on a card block.** Two arithmetic
consequences of A5 as written, both of which break the demo script and, more
importantly, the tier definitions the synopsis gives.

*First.* A5 says `s_verify` is "0 when no verification has run", so the
`w3 * (1 - s_verify)` term contributes a flat 0.25 to every unverified turn.
Since `t1 = 0.25`, every unverified turn is at least tier 1, and tier 0
("public information, no authentication") can never occur. *Resolution
applied:* for intents that need no identity at all (`product_info`,
`branch_ifsc`, `out_of_scope`) there is no verification deficit, so the term
contributes zero. The trace records `identity_required: false` so the zero is
explained rather than unexplained.

*Second.* With `sens(block_card) = 0.70` and `w1 = 0.40`, a fully verified
card block scores `R = 0.28`, which is tier 1. It would then skip the OTP and
the spoken read-back, even though the synopsis defines tier 2 as the
transactional tier and beat 6 of the demo expects it. *Resolution applied:* a
per-intent minimum tier, `MIN_TIER_BY_INTENT` in config. The score can raise a
turn above its floor but never below it. This is the same mechanism as the
tier 3 hard override applied one level down, and it is a cleaner safety
property to state in the paper than a tuned weight would be: an action that
mutates account state never drops below the confirmation tier however
confident the system is about who is speaking.

Both are tested in `tests/test_risk.py`. Both are reversible by editing
`PUBLIC_INTENTS` and `MIN_TIER_BY_INTENT` in `config.py`. An alternative
resolution would be to retune `w` and the cut-points instead, which would make
the tier a pure function of the score; that was rejected because it makes the
safety property depend on arithmetic that a future weight change could quietly
break.

## 6. Substitutions

Every production component the synopsis names is substituted for something
demo-sized. The full table with reasons is in `STACK_MAPPING.md`. The
substitutions are scoping decisions and are all recorded; none of them is
hidden behind a component that claims to be the real thing.

## 6b. Known gaps, found by building it

These are not conflicts with the source documents. They are things the working
system revealed, listed so the next person does not have to rediscover them.

**A monolingual knowledge base plus one global similarity floor refuses
non-English speakers.** The policy documents are written in English. The same
question asked in Marathi scores a mean top similarity of 0.31 against 0.72 for
English, purely through the cross-lingual gap in the embedding, so the floor
calibrated on the whole set refuses 0 of 2 Marathi queries that are perfectly
answerable. This directly undercuts the project's own inclusion argument, and
it is measured and printed in RESULTS.md rather than averaged away. Two fixes
are obvious and neither is implemented: a per-language floor, or translated
passages in the knowledge base. This belongs in the paper as a result.

**Language identification on romanised Indic text is the weak link.** Dominant
language accuracy is 0.74. Romanised Hindi and Marathi words outside the seeded
function-word lexicon fall through to English. The Viterbi smoother is sound
and takes posteriors from any source; the prior feeding it is what needs
replacing with a trained head.

**The evaluation audio for Hindi, Marathi and code-mixed utterances is not a
valid test.** Those references are romanised Latin text rendered through a
Devanagari voice, which produces mispronounced audio. The near 1.0 word error
rates on those rows measure the rendering, not the recogniser. Recorded human
audio is the single highest value next step for the evaluation.

**A compound request is correctly refused and it looks like a failure.** "Mera
balance kitna hai, and last three transactions bhi bata do" splits the intent
head almost evenly between two trained classes, confidence fusion falls just
under tau, and the turn escalates. That is the designed behaviour and a good
story, but only if the presenter explains it before the panel asks. The runbook
now does.

**The anti-spoof measurement compares two synthesis conditions.** No human
speech is collected, so both the bona fide and the spoof class come from a text
to speech system. The countermeasure is real and the number is real; what it
measures is not what the label suggests, and RESULTS.md says so next to the
figure.

## 6c. Fixed after a tester recorded it

An 88 second recording of the system in use produced four defects that no test
had caught, which is worth stating plainly: the test suite was green
throughout. Each is now covered.

**Romanised Hindi and Marathi.** Both speech engines phonemise from script, so
every romanised reply was read with English vowels. Fixed in Devanagari, with
`tts.assert_devanagari` raising rather than warning and
`tests/test_tts_language.py` walking every template. The lesson is that a
correctness property nothing can observe from the outside needs an assertion,
not a convention.

**One garbled transcript ended the call.** See A5's ratchet guards. The
security property survived; the failure mode did not.

**Verification that verified nothing.** Text turns re-scored a seeded WAV and
reported it as the caller's check, and choosing a customer without a seeded
clip crashed the turn. A check is now a live recording with an expiry, and the
fallback declares itself SIMULATED.

**A refusal by one hundredth.** The similarity floor was calibrated to F1 on a
54 item set, landed on 0.59, and refused a real spoken question that scored
0.58. Fixing it exposed a worse problem underneath: the negative class was
wrong. See A4.

## 6d. Investment questions and the advice boundary

Callers ask about stocks. The obvious build is to let the assistant answer,
and it is the wrong one.

Factual questions are answered: what a demat account costs, what the lock in
on an ELSS fund is, what a customer's own holdings are worth today. Those are
numbers already in a record, and the intent `investment_info` handles them at
tier 1, since holdings are account data.

"Which stock should I buy", "is this a good time", "suggest a better option"
are a different thing. Under the SEBI (Investment Advisers) Regulations 2013
that advice may be given only by a registered investment adviser, and an
automated assistant is not one. So `investment_advice` is a hard tier 3
alongside `fraud_report`: mandatory human handover, unreachable by
automation, whatever the confidence. The caller is told why rather than
transferred in silence, and a test asserts the refusal contains no hedged
recommendation, because a hedged recommendation is still a recommendation.

One refinement came out of testing it. Asking for advice is not a risk
signal, so unlike a fraud report it does not raise the session tier floor.
Without that carve-out, `NON_RATCHETING_TIER3`, asking about stocks locked
the caller out of their own balance for the rest of the call. Wanting a human
(`agent_request`) is in the same set for the same reason.

This is a stronger result for the paper than a stock recommender would have
been: the interesting claim is that the system knows the edge of its own
authority and stops there.

## 6e. The demo persona

`CUST9001` is a fuller synthetic customer than the twenty the seed script
generates: two accounts, two cards, three payees, a month of realistic
transactions, six holdings, two systematic plans. It exists so a presenter
can be asked an unscripted question and the system has something true to say.

A presenter enrols their own voice against it through `POST /enroll`, which
replaces the synthetic embedding and flips the enrolment source to `live`.
The display name comes from `BFSI_PRESENTER_NAME` at runtime rather than from
a committed file, because the repository rule is that no real personal data
lives in it, and a name is personal data.

## 7. Where to look in the code

| Concern | File |
| --- | --- |
| The trace object | `backend/app/trace.py` |
| Every threshold and weight | `backend/app/config.py` |
| What is real and what is not | `backend/app/capabilities.py` |
| Turn orchestration | `backend/app/turn.py` |
| Code-switch language ID | `backend/app/pipeline/langid.py` |
| Risk, fusion, the gate | `backend/app/pipeline/dialogue.py` |
| Retrieval and the refusal floor | `backend/app/pipeline/retrieval.py` |
| Hash chain and tamper localisation | `backend/app/security/ledger.py` |
| Luhn, Verhoeff, redaction | `backend/app/security/pii.py` |
| Speaker verification | `backend/app/security/speaker.py` |
| Anti-spoof baseline | `backend/app/security/antispoof.py` |
| Metrics | `backend/app/eval/metrics.py` |
