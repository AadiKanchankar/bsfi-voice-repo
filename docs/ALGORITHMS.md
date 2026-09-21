# Algorithms

Each section gives the formula as implemented, the complexity, the parameter
values chosen and where they came from, and the test that pins the behaviour.
Parameter values marked *measured* are written by `make eval` into
`runtime/calibration.json` and override the config defaults at import time, so
the running system uses the number that was actually measured.

All symbols map to names in `backend/app/config.py`.

---

## A1. Code-switch-aware language identification

**Problem.** Per-word language evidence is noisy. Taken at its argmax it flips
every second word, which produces spans no reviewer can read and a TTS voice
that changes mid-sentence.

**Method.** Viterbi over a language state machine with a penalty for switching.
For word `i` and language `l`, with per-word posterior `p_i(l)`:

```
score(i, l) = log p_i(l) + max over l' [ score(i-1, l') - eta * 1[l != l'] ]
```

Backtrack for the best path, then merge maximal same-language runs into
`LanguageSpan` objects.

**Parameters.** `eta = 2.0` (`SWITCH_PENALTY_ETA`), languages `{en, hi, mr}`,
posterior floor `1e-6` so `log` stays finite.

At `eta = 0` the output is the raw argmax. As `eta` grows the tagger prefers
longer runs; in the limit it collapses to one language for the whole utterance.
`eta = 2.0` was chosen as the smallest value that suppresses flapping on
near-tied posteriors (0.55 against 0.54) while leaving a genuine switch backed
by strong evidence (0.98 against 0.01) intact. Both behaviours are asserted:
`test_langid.py::test_switch_penalty_reduces_flapping` and
`::test_strong_evidence_survives_the_penalty`.

**Posterior source.** A script and lexicon prior, not a trained LID head:
Devanagari rules out English outright, function-word lexicons separate Hindi
from Marathi, and an unseen Latin-script token leans mildly English because the
BFSI lexicon (IFSC, NEFT, product names) is written in English everywhere. The
registry records this in the `langid` note. `viterbi_smooth` takes posteriors
as an argument, so a trained head drops in without touching the smoother.

**Code-mix index.**

```
CMI = 100 * (1 - max_l(n_l) / n_total)      for n_total > 0
```

`CMI = 0` is monolingual. An even two-way split is 50. Reported per utterance
and shown on the dashboard.

**Complexity.** `O(n |L|^2)` time, `O(n |L|)` space. At utterance length this
is nothing.

**Why it is worth writing up.** Most deployed pipelines run language
identification once per call. The synopsis argues code-mixing is the normal
case for this user base, and a per-call decision cannot represent it at all.

---

## A2. Confidence fusion

```
c_final = c_asr^alpha * c_intent^beta * c_retr^gamma        alpha + beta + gamma = 1
```

**Parameters.** `alpha = 0.30`, `beta = 0.45`, `gamma = 0.25`. `c_retr = 1` for
intents that need no grounding.

**Why geometric.** So that one weak signal can veto automation on its own. With
`c_asr = 0.05` and everything else at 0.99, the geometric fusion gives about
0.35 while a weighted average gives about 0.94. An average lets a confident
intent hide a terrible transcript, which is exactly the failure this system
exists to catch. Asserted in `test_risk.py::test_fusion_is_geometric_and_vetoable`.

**Complexity.** `O(1)`.

---

## A3. Intent classification and slot extraction

**Intent.** The utterance is embedded with
`paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, frozen) and
classified with multinomial logistic regression, `C = 8.0`,
`class_weight="balanced"`, `max_iter = 2000`. The softmax posterior is
`c_intent`. The runner-up is also recorded: a turn where the top two intents
are 0.34 and 0.33 is a turn that should not be automated, and the dashboard
shows the gap.

**Training data.** `data/seed/intent_bank.yaml`, 397 utterances across 14
intents, minimum 25 per intent, spread over English, Hindi (romanised and
Devanagari), Marathi and code-mixed forms. `out_of_scope` carries 58, the most
of any class and the widest variety, because it is what protects the refusal
path; a thin `out_of_scope` class is how a banking bot ends up confidently
answering a question about the CEO's phone number.

**Complexity.** One embedding forward pass plus a `14 x 384` matrix multiply.

**Slots by rule, not by model.** Rules are auditable, which is the point. A
compliance officer can read the regular expression that pulled "fifty
thousand" out of an utterance; they cannot read a sequence tagger's weights.

Amount parsing handles Indian numbering in three languages: digits with
multipliers (`2 lakh`, `25,000`), and word numbers in English, Hindi and
Marathi (`fifty thousand`, `pachas hazaar`, `do lakh`). A bare number under 100
with no currency cue nearby is rejected, so "my last three transactions" does
not become an amount of three. Amount is the single most dangerous slot in the
system and carries the most tests.

Other slots: card and account last four, payee name (only for transfer
intents), date range, cheque number, product name.

---

## A4. Retrieval grounding with an explicit refusal path

**Indexing.** Policy documents are chunked by `##` heading, which is how a
policy document is actually organised and therefore the natural unit to cite
back to a customer. Each chunk carries `doc_id`, `version`, `effective_date`,
`section` and `category` from the YAML front matter.

**Search.**

1. Embed the query, cosine against all chunks (vectors are L2-normalised, so
   the cosine is a dot product).
2. Maximal Marginal Relevance over the top `5k` candidates:

```
MMR = argmax_d [ lambda * sim(d, q) - (1 - lambda) * max_{d' in S} sim(d, d') ]
```

   with `lambda = 0.7`. Without this, three near-identical chunks from one
   document fill the top k and the citation list looks thorough while covering
   one source.
3. Keep the top `k = 4` that clear the similarity floor `delta`.
4. **If nothing clears `delta`, refuse.** There is no generation step that
   could paper over an empty result. `decision = "refused"`, the max score
   achieved is recorded, and the assistant offers a human agent.

**Version awareness.** When two versions of one `doc_id` both match, the
superseded version is excluded from the answer and kept in the trace under
`superseded_versions`, so the dashboard can show that version 1.1 was cited and
1.0 was deliberately not. `POL-HL-001` is seeded at two versions for exactly
this.

**delta.** Default `0.42`. *Measured*: `make eval` calibrates it and writes
the result to `runtime/calibration.json`. Two corrections to the naive recipe,
both forced by testing:

*The negative class is `out_of_scope`, not "everything the knowledge base does
not answer".* Those are different sets. "What is the balance in my savings
account" scores 0.77 against the savings-account policy, correctly, because
such a policy exists; it is answered from core banking rather than from the
knowledge base, which makes it neither a grounding positive nor a must-refuse
negative. Counting it as a false positive drove the floor to 0.645 and dropped
recall on genuinely answerable questions to 0.5. Account and transaction
queries are now excluded from the calibration and reported separately.

*The objective is the lowest floor meeting a precision constraint, not maximum
F1.* F1 on a 54 item set over-fits: it chose 0.59, and a real spoken question
about home loan rates then scored 0.58 and was refused on air. The system now
takes the lowest floor whose precision still clears 90 percent. The asymmetry
is deliberate. A weak passage is still cited, still version-stamped and still
gated by the confidence and tier machinery downstream; a wrong refusal just
sends the customer away. Both candidates are printed in RESULTS.md so the
choice is visible.

**Complexity.** `O(N d)` for the scan over `N` chunks of dimension `d`, plus
`O(k^2 c)` for MMR over `c` candidates. With `N` in the low hundreds this is
sub-millisecond, which is why there is no vector index.

---

## A5. Risk scoring and tier assignment

```
R = w1*sens(intent) + w2*norm(amount) + w3*(1 - s_verify) + w4*dev(history)
```

with `sum(w) = 1` and `w = (0.40, 0.25, 0.25, 0.10)`.

**sens(intent)** from `INTENT_SENSITIVITY`, range 0 to 1. `product_info` 0.05,
`branch_ifsc` 0.05, `cheque_status` 0.20, `apply_loan` 0.25, `get_balance`
0.35, `mini_statement` 0.35, `add_payee` 0.55, `limit_change` 0.60,
`block_card` 0.70, `fund_transfer` 0.85, `dispute_txn` 0.90, `agent_request`
0.90, `fraud_report` 1.00, `out_of_scope` 0.10.

**norm(amount)** `= min(1, log1p(a) / log1p(A_max))`, `A_max = 200000`. Log
scale, because the step from 1,000 to 10,000 rupees changes the consequence of
an error far more than the step from 190,000 to 200,000. Asserted in
`test_risk.py::test_norm_amount_is_log_scaled`.

**s_verify** is the speaker verification score in `[0, 1]`, defined as
`s_cos * spoof_score`, or 0 when no verification has run. A turn with no
verification therefore contributes the full `w3` to the risk, which is the
intended behaviour: absence of evidence raises risk.

**dev(history)** `= 1 - exp(-lam * n)`, `lam = 0.5`, saturating so a session
with six anomalies is not treated as six times worse than one with a single
anomaly. Anomalies counted: `new_device`, `unusual_hour` (outside 06:00 to
22:00 local), `first_ever_payee`, `rapid_repeat_attempts` (three or more turns
within 60 seconds). Each is recorded by name in the trace, not just as a count.

**Tiers.** Cut-points `t = (0.25, 0.50, 0.75)`.

- Tier 0, public information, no authentication.
- Tier 1, account-specific, passive speaker verification.
- Tier 2, transactional, verification plus OTP plus a spoken read-back before
  the action commits.
- Tier 3, mandatory human handover with the context packet.

**The verification term applies only when identity is in scope.** For
`product_info`, `branch_ifsc` and `out_of_scope` the term contributes zero
rather than `1 - 0 = 1`. Taking A5 literally, every unverified turn would
carry a flat `w3 = 0.25`, which equals `t1` exactly and makes tier 0
unreachable, contradicting its own definition. The trace records
`identity_required` so the zero is explained. See ARCHITECTURE.md conflict C9.

**Three safety properties, enforced rather than hoped for.**

*Hard override.* `fraud_report`, `dispute_txn` and `agent_request` are tier 3
regardless of the score. A bug in the arithmetic must never be able to automate
a fraud report. `test_risk.py::test_hard_override_beats_any_score`.

*Session tier ratchet.* Within a session the tier is monotonically
non-decreasing, and the floor is persisted in the `sessions` table so it
survives a reconnect. An attacker cannot lower their own risk by asking an
innocent question after a refused transfer.
`test_risk.py::test_session_ratchet_never_de_escalates`.

*Ratchet guards.* The ratchet as first written had a failure mode that testing
found within one session: a misheard "mera balance kitna hai" was classified
`dispute_txn`, which hard-overrides to tier 3, and the floor then pinned every
later turn at tier 3 including public-information questions. Three guards keep
the security property and remove the failure:

  - the floor only rises on an escalation where intent confidence clears
    `RATCHET_MIN_INTENT_CONFIDENCE` (0.55). A low-confidence turn still
    escalates, which is safe; it just does not pin the call.
  - public-information intents are exempt from the floor entirely. They touch
    no account and reveal nothing identity-bound, so answering one at tier 0
    after an escalation leaks nothing an attacker could not read on the
    website.
  - the floor decays one tier per `RATCHET_DECAY_AFTER_CLEAN_TURNS` (3)
    consecutive turns that raise no new escalation.

*Per-intent tier floor.* `MIN_TIER_BY_INTENT` sets a lower bound the score
cannot go under: 1 for account-specific reads, 2 for anything that mutates
account state, 3 for the hard overrides. A fully verified caller asking to
block a card scores `R = 0.28`, which is tier 1 on the cut-points alone and
would skip the OTP and the read-back. The floor prevents that. The score can
still raise a turn above its floor, which is what the amount and anomaly terms
are for. `test_risk.py::test_intent_floor_holds_even_with_perfect_verification`.

The applied tier is therefore `max(scored_tier, intent_floor, session_floor)`,
and all three are recorded in the trace so the dashboard can say which one
bound.

**The automation gate.** A turn is automated only when all of:

1. `R < t_tier`
2. `c_final >= tau_tier`, with `tau = (0.50, 0.62, 0.75, 1.01)`
3. speaker verification passed, if the tier requires it
4. retrieval cleared `delta`, if the intent needs grounding
5. for tier 2, OTP accepted and the read-back confirmed

`tau[3] = 1.01` is above the maximum possible confidence, so tier 3 is
unreachable by construction and not merely by policy.

Note on condition 1: because the tier is derived from `R`, `R < t_tier` holds
by construction whenever the tier was not raised by the override or the
ratchet, and raising the tier only makes it hold more easily. It is therefore
an invariant check rather than a discriminating condition, and it is kept
because a future change to tier assignment could break it silently. The work of
refusing is done by conditions 2 to 5. Stated here so a reviewer is not misled
into thinking it filters anything today.

The first failing condition becomes `decision_reason`, and the whole checklist
with pass or fail per row goes into the trace and onto the dashboard.

**Refuse or escalate.** A grounding failure is a refusal: there is no answer to
give. Everything else escalates to a human, because the customer still has a
problem that somebody has to solve. A tier 0 confidence failure also refuses,
since a low-confidence public-information query does not need an agent.

**Complexity.** `O(1)`.

---

## A6. Speaker verification and anti-spoofing

**Enrolment.** Three utterances, ECAPA-TDNN embedding each, L2-normalise, take
the mean, L2-normalise again. The mean pairwise cosine of the enrolment clips
is reported at enrolment time so a bad enrolment is visible then rather than at
verification time.

**Verification.** `s = cos(x_e, x_t)`, accept above `theta`.

**When a verification counts.** A check is evidence about who is speaking now,
so it expires: five minutes or five turns, whichever comes first. A typed turn
carries the last live check and consumes one of its turns. What it never does
is re-score a stored clip and report that as the caller's verification, which
is what the first build did and why a tester reached account data without ever
being checked. The dead-microphone fallback still exists and is reported as
SIMULATED on every turn it carries.

**theta.** Default `0.35`. *Measured*: set at the Equal Error Rate on the
synthetic trial set by `make eval`, written to `runtime/calibration.json` and
read at import. RESULTS.md prints the measured EER and the trial counts. The
EER sweep evaluates every distinct score in the pooled set, so the reported
crossing point is real and not interpolated between coarse bins.

**Anti-spoofing, `BASELINE`.** Linear frequency cepstral coefficients, 20
filters, 20 coefficients, plus delta and double delta features, 25 ms frames
with a 10 ms hop. Two diagonal-covariance Gaussian mixtures, one for bona fide
and one for spoof, up to 8 components. Score is the log-likelihood ratio mapped
through a logistic:

```
llr   = log p(x | bona fide) - log p(x | spoof)
score = 1 / (1 + exp(-llr / 2))
```

Linear rather than mel filter spacing, because mel spacing compresses exactly
the high frequency detail where vocoder artefacts live.

The score multiplies the speaker cosine, `s_verify = s_cos * spoof_score`, so a
suspected spoof drags verification down and raises `R` rather than acting as a
separate yes-or-no gate. That is what the synopsis specifies.

The interface is the durable part:

```python
class AntiSpoofScorer:
    def score(self, audio) -> float:   # 1.0 means bona fide
```

A trained AASIST drops in behind that signature with no change above this file.

**t-DCF.** Reported alongside EER, using the ASVspoof 2019 normalised minimum
formulation with the ASV system fixed at its own measured operating point:

```
C1 = pi_tar * (C_miss - C_miss * P_miss_asv) - pi_non * C_fa * P_fa_asv
C2 = C_fa * pi_spoof * P_fa_spoof_asv
t-DCF_norm(s) = (C1 * P_miss_cm(s) + C2 * P_fa_cm(s)) / min(C1, C2)
```

with `C_miss = 1.0`, `C_fa = 10.0`, `pi_target = 0.05`, `pi_spoof = 0.05`. The
constants are printed beside the number in RESULTS.md so it can be reproduced.

**The honest caveat, repeated wherever the number appears.** No human speech is
collected in this build, so both the bona fide and the spoof class originate
from a text to speech system. Bona fide clips are enrolment-voice renderings
passed through a simulated telephony channel (300 to 3400 Hz band pass, mild
additive noise, gain variation); spoof clips are clean wideband renderings of
the same phrases in a different voice, modelling a cloned-voice injection. The
measured EER and t-DCF therefore characterise the separation of two synthesis
and channel conditions, not human speech from deepfakes. `POST /enroll` accepts
a real voice, at which point the bona fide class becomes genuine.

---

## A7. PII redaction before persistence

Runs before anything touches disk. Raw audio lives in memory only for as long
as transcription needs it and is dropped immediately after; there is a test
asserting no raw audio file exists once a turn completes.

**Detection order matters.** PAN first because its pattern is unambiguous, then
email, then card (Luhn validated), then Aadhaar (Verhoeff validated), then
phone, then generic account numbers. On overlap the longest match at the
earliest position wins, so a card number is not partially eaten by the
account-number pattern. Anything that fails its checksum is not tokenised as
that type.

**Luhn.** Mod-10. Double every second digit from the right, subtract 9 from any
result above 9, and the total must be divisible by 10. `O(n)`.

**Verhoeff.** Dihedral group D5. Multiplication table `d`, position permutation
`p` with period 8, inverse table `inv`:

```
c = 0
for i, digit in enumerate(reversed(digits)):
    c = d[c][p[i % 8][digit]]
valid if c == 0
```

`O(n)` with three table lookups per digit. Verhoeff is the reason a random
twelve-digit reference number is not tokenised as an Aadhaar number, which is
asserted directly in `test_pii.py::test_random_12_digits_is_not_aadhaar`.

**Spoken digits.** ASR writes "my account is four five six seven" as words, and
a redactor that only reads `/\d/` lets it straight through to disk. Runs of
four or more consecutive digit words in English, Hindi or Marathi, including
"oh" for zero and the multipliers "double" and "triple", are recovered to
digits, checksum tested, and tokenised as CARD, AADHAAR or ACCT accordingly.
Four is the minimum run length, below which a number word is a quantity rather
than an identifier.

**Tokens.** `<PAN_1>`, `<ACCT_2>` and so on. Counters and the value-to-token
map are per session, so `<ACCT_1>` means the same account on turn 5 as it did
on turn 1. Raw values go into a per-session AES-256-GCM vault held in its own
table, with the session id as additional authenticated data so a row moved
between sessions fails to decrypt. The transcript store holds tokens only.

**Consent withdrawal** purges the vault rows and the transcripts for the
session and appends a purge record to the ledger. The ledger itself is not
deleted: it holds hashes and tokens, never identifiers, and deleting it would
destroy the evidence that the purge happened.

---

## A8. Tamper-evident ledger

```
H_i   = SHA256( H_{i-1} || canonical_json(M_i) || t_i )
sig_i = HMAC-SHA256( key, H_i )
```

Genesis `H_0` is 64 zeros, fixed in config. Canonical JSON means sorted keys
and fixed separators; if the serialisation is not byte-identical on replay the
whole structure proves nothing, so every hash in the system goes through one
function. The HMAC key is never stored in the database.

**Three independent checks per record.**

| check | catches |
| --- | --- |
| `link` | `prev_hash` of record i does not equal `hash` of record i-1: deletion, reordering, insertion |
| `binding` | `hash` of record i does not equal `SHA256(prev_hash \|\| payload \|\| ts)`: a payload edited in place |
| `sig` | HMAC does not match: an attacker who recomputed hashes but has no key |

Beat 10 of the demo is a `binding` failure: `scripts/tamper_demo.py` runs a
plain SQL `UPDATE` on one payload field and recomputes nothing.

**Checkpoints.** Every `k = 64` records the chain head is written to
`ledger_checkpoint`, giving segment anchors.

**Complexity, stated precisely because the paper repeats it.**

| operation | cost |
| --- | --- |
| append | `O(1)`, one SHA-256 and one HMAC |
| full verify | `O(n)` |
| localise, corruption reaching the end of the chain | `O(log(n/k))` probes of `O(k)` each |
| localise, single isolated payload edit | walk the `n/k` anchors in order, `O(n)` hashes |

The second row is the rewriting-attacker case: every segment after the edit
fails its anchor check, the failure is monotone in the segment index, and
binary search applies. Measured on a 1000-record chain with a rewrite at index
900, the checkpoint search touches 148 records against 901 for the linear scan.

The third row is the honest limit. A single edited payload that leaves every
stored hash untouched breaks nothing downstream, so no anchor after it
disagrees and no search can skip segments without risking missing it. That is
information-theoretic, not an implementation gap: locating one modified record
in `O(log n)` requires a Merkle tree, which is the stretch goal. The
implementation runs the binary search first and falls back to an in-order walk,
so the located record always matches the linear scan. Both cases are asserted,
including 20 randomised corruptions compared against the linear result
(`test_ledger.py::test_checkpoint_search_matches_linear`).

**Export.** `GET /ledger/export` returns the full chain, the checkpoints and a
detached HMAC signature over the canonical JSON of the whole export.

---

## A9. Evaluation metrics

**WER** `= (S + D + I) / N` from a Levenshtein alignment with backpointers,
`O(|ref| * |hyp|)`. The alignment is written out rather than imported because
the entity metric needs the alignment itself, not the distance. Corpus WER is
pooled over the whole set, not averaged per utterance, since averaging
over-weights short utterances.

**Entity-level error rate** `EER_s = (1/|E|) * sum_i 1[e_hat_i != e_i]` over
financial entities, reported per type: amount, payee, product name, card last
four, cheque number.

Each labelled entity is located in the reference by trying token n-grams up to
length 4 and comparing canonical forms, which is necessary because the label
says `50000` and the transcript says "fifty thousand". That reference span is
mapped onto hypothesis tokens through the WER alignment, and the mapped text is
canonicalised and compared. Amounts are canonicalised through the same parser
the pipeline uses, so the metric measures what the system would actually have
extracted.

An entity whose reference span cannot be located is counted as an error, not
skipped. Silently dropping hard cases would flatter the number.

**Recall@k** for retrieval over the answerable queries, and the tuned `delta`
reported with its F1 and both class sizes.

**Speaker EER** and **min t-DCF** as in A6.

**Latency** p50 and p95 per stage, read straight off the trace timings, plus a
turn total.

**Evaluation set.** 54 hand-labelled utterances: 28 English, 10 Hindi, 8
Marathi, 8 code-mixed; 18 answerable from the policy knowledge base and 36 not,
which is what makes the `delta` calibration meaningful. Audio is rendered with
Piper, so WER measured here is optimistic relative to human telephony audio.
The set size is printed next to every number in RESULTS.md, and the caveats are
repeated there rather than being stated once and forgotten.
