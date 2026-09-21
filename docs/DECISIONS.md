# Decision log

Numbered, append-only. Every entry: the context, the options considered, the
choice, and why. A decision is reversed by adding a new entry that supersedes
the old one, never by editing history.

The graph in `graphify-out/` remembers structure. This file remembers
judgement, which is the part that cannot be re-derived by reading the code.

Status values: **applied**, **pending sign-off**, **superseded**, **rejected**.

---

## D1. Four layers, not three
*Applied. Migrated from ARCHITECTURE.md conflict C1.*

**Context.** The build prompt asked for a four-layer architecture "matching
Figure 1 of the synopsis". The paper's Section III describes three: Core
Voice and AI, Integration Middleware, Admin Dashboard.

**Options.** (a) Three layers, following the paper. (b) Four, splitting
compliance out of middleware.

**Choice.** Four. The synopsis abstract separately names "secure middleware
and a compliance layer", and the separation is the project's whole argument:
compliance owns the object the other layers write through, rather than being
a sink they report into.

**Reversal cost.** One line in `scripts/diagrams/generate.py`.

---

## D2. Three languages, not five
*Applied. Migrated from C2.*

**Context.** Synopsis objective 1 commits to "at least five Indian
languages". The build prompt scopes the demo to English, Hindi and Marathi.

**Choice.** Three, as the prompt says. `config.LANGUAGES` holds the list and
the Viterbi tagger is written for an arbitrary state set, so a fourth
language is a config entry plus a lexicon, not a rewrite.

**Honesty note.** This gap is stated in the review, not hidden. It is a
scope decision, not a capability claim.

---

## D3. Anti-spoofing is a classical baseline, not AASIST
*Applied. Migrated from C3.*

Synopsis and paper both name an AASIST-style countermeasure. A trained AASIST
is out of scope. Shipped: LFCC features with a two-class GMM log-likelihood
ratio, registered `BASELINE`, labelled as such in the registry, the trace,
the dashboard and RESULTS.md.

---

## D4. The ASR is not fine-tuned on banking audio
*Applied. Migrated from C4.*

The synopsis describes Whisper fine-tuned on a banking corpus. No fine-tuning
happens here. The measured entity-level error rate is therefore framed as the
baseline a fine-tuned model must beat, which is a stronger claim than
pretending otherwise.

---

## D5. Hash chain, not blockchain
*Applied. Migrated from C5.*

The paper retains the base system's blockchain audit trail. The synopsis
already argues for "simpler, cryptographically signed logging". Shipped:
SHA-256 hash chain with HMAC-SHA-256 signatures and checkpoints.

**Action outstanding.** The paper's Section IV comparison table still claims
blockchain and should be updated before submission.

---

## D6. A logic inversion in the paper
*Applied, documentation only. Migrated from C6.*

Paper Section III.D reads "decides whether the query is simple enough to be
automated without human intervention, if yes the query is routed to the
humans". The condition is inverted; it should read "if no". Worth fixing
before the camera-ready version.

---

## D7. Two different things were both called EER
*Applied. Migrated from C7.*

The synopsis uses `EER_s` for entity-level error rate and EER for the equal
error rate of speaker verification. The code calls them `entity_error_rate`
and `eer` and never abbreviates the first. RESULTS.md spells both out.

---

## D8. Tamper localisation is not O(log n) for an isolated edit
*Applied. Migrated from C8.*

**Context.** The prompt states localisation is `O(log n) + O(k)` by binary
search over checkpoints.

**What is actually true.** That holds when the corruption propagates to the
end of the chain, which is the case when an attacker rewrites hashes forward.
A single edited payload that leaves every stored hash untouched breaks
nothing downstream, so no checkpoint anchor disagrees and no search can skip
segments without risking missing it. That is information-theoretic, not an
implementation gap.

**Choice.** Implemented as specified, with an in-order fallback so the
located record always matches the linear scan. Both cases are asserted in
`tests/test_ledger.py`, including twenty randomised corruptions. Measured on
a 1000-record chain with a rewrite at index 900, the checkpoint search touches
148 records against 901 for the linear scan.

**What would make the claim true.** A Merkle tree, which is listed as a
stretch goal. `verify()` keeps its signature either way.

---

## D9. The specified risk formula made tier 0 unreachable
*Applied. Migrated from C9. This one changed behaviour, so read it.*

**Context.** Two arithmetic consequences of the formula as written.

*First.* A5 says `s_verify` is "0 when no verification has run", so the
`w3 * (1 - s_verify)` term contributes a flat 0.25 to every unverified turn.
Since `t1 = 0.25`, every unverified turn was at least tier 1, and tier 0
("public information, no authentication") could never occur.

*Second.* With `sens(block_card) = 0.70` and `w1 = 0.40`, a fully verified
card block scores `R = 0.28`, which is tier 1. It would skip the OTP and the
spoken read-back, though the synopsis defines tier 2 as the transactional
tier.

**Options.** (a) Retune the weights and cut-points so the tier is a pure
function of the score. (b) Add structural rules the score cannot override.

**Choice.** (b). Public-information intents carry no verification deficit, so
the term contributes zero for them, and `MIN_TIER_BY_INTENT` sets a floor the
score can raise but never go under. Rejected (a) because it makes a safety
property depend on arithmetic a future weight change could quietly break.

**Reversal.** Edit `PUBLIC_INTENTS` and `MIN_TIER_BY_INTENT` in `config.py`.

---

## D10. The session tier ratchet needed three guards
*Applied.*

**Context.** A tester's recording showed one garbled transcript ("mera balin
skit na hai") classified as `dispute_txn` at 0.16 confidence, which hard
overrides to tier 3 and pinned the session floor there. Every later turn
escalated, including a plain request for published interest rates.

**Choice.** Keep the ratchet, add three guards: the floor only rises on an
escalation whose intent confidence clears 0.55; public-information intents
are exempt from the floor entirely; and the floor decays one tier per three
consecutive clean turns.

**Why not remove the ratchet.** It stops an attacker lowering their own risk
by asking an innocent question after a refused transfer. That property is
worth keeping; the failure mode was the unconditional application of it.

---

## D11. Not every tier 3 is a risk signal
*Applied.*

`agent_request` and `investment_advice` escalate the turn but do not raise
the session floor (`NON_RATCHETING_TIER3`). A fraud report or a dispute says
the account may be compromised. Asking to speak to a human, or asking for
investment advice, says nothing about risk. Without this, asking about stocks
locked the caller out of their own balance for the rest of the call.

---

## D12. Investment advice is refused, not answered
*Applied.*

**Context.** A request to let the assistant answer stock questions and
"return with a better option".

**Choice.** Split into two intents. `investment_info` answers facts: product
features, published rates, charges, and the value of a customer's own
holdings. `investment_advice` (which stock to buy, whether now is a good
time, which fund is better) is a hard tier 3 mandatory handover.

**Why.** Under the SEBI (Investment Advisers) Regulations 2013 such advice
may be given only by a registered investment adviser, and an automated
assistant is not one. A hedged recommendation is still a recommendation, so
there is a test asserting the refusal contains no hedging.

**Why it is a better result than a recommender.** The interesting claim for
the paper is that the system knows the edge of its own authority.

---

## D13. Hindi and Marathi replies are written in Devanagari
*Applied.*

**Context.** A tester reported the Hindi "feels very different". Every Hindi
and Marathi reply template was romanised Latin. Both offline speech engines
phonemise from script, so espeak's Hindi phonemiser read Latin letters with
English vowels: "khatam hone wale" became `kˈɑːtam hˈəʊn wˈeɪl`.

**Choice.** Every template rewritten in Devanagari, with
`tts.assert_devanagari` raising rather than warning, and a test walking every
template. Verified by transcribing the new audio back: it recovers the
intended sentence nearly word for word, where the old audio came back as
gibberish.

**The general lesson.** A correctness property nothing can observe from
outside needs an assertion, not a convention.

---

## D14. The similarity floor was calibrated against the wrong negative class
*Applied.*

**Context.** A recorded session showed a refusal at 0.58 against a floor of
0.59, on a question the knowledge base answers.

**Two faults.** The floor was tuned to maximum F1 on a 54-item set, which
over-fits. Worse, the negative class was "everything the knowledge base does
not answer", which wrongly included account queries: "what is the balance in
my savings account" scores 0.77 against the savings policy, correctly,
because such a policy exists. Counting that as a false positive drove the
floor to 0.645 and dropped recall to 0.5.

**Choice.** Negatives are `out_of_scope` only. Account and transaction
queries are excluded from the calibration and reported separately. The
objective is the lowest floor whose precision still clears 90 percent, not
maximum F1.

**Result.** Floor 0.50, precision 0.94, recall 0.89. Hindi answerable queries
clearing the floor went from 0 of 2 to 2 of 2, code-mixed 0 of 2 to 2 of 2.

---

## D15. Verification expires
*Applied.*

**Context.** A tester enrolled a voice, was asked to verify, and reported
that it "clearly didn't verify". Two faults: choosing a customer with no
seeded clip crashed the turn with `FileNotFoundError`, and text turns
re-scored a stored WAV from disk and reported it as the caller's
verification, which is replaying a recording of a check rather than checking.

**Choice.** A voice check is a live recording with a TTL: five minutes or
five turns. Typed turns carry the last check and consume one of its turns.
The dead-microphone fallback still exists and is reported `SIMULATED` on
every turn it carries.

---

## D16. The CLU may raise risk and never lower it
*Applied.*

**Context.** Adding a contextual language layer to handle code-mixing,
compound requests and follow-ups.

**Choice.** The deterministic classifier runs on every turn regardless. The
model proposes; a merge decides. If either reading is a hard tier 3 intent,
or the deterministic reading is more sensitive and was confident, the
deterministic one is kept. Rule-based slots win over model entities on any
key the rules extracted.

**One carve-out, added after testing.** An absolute floor was worse: the
deterministic head fired `fraud_report` at 0.30 on the harmless follow-up
"aur uske pehle wali?", and the unconditional rule pinned that turn to
mandatory handover. A downgrade from a hard-handover intent now requires both
an unconfident deterministic reading (below 0.45) and a confident model one
(above 0.70), and every occurrence is recorded.

**Result.** Intent accuracy on a deliberately hard 40-case set went from 0.65
to 0.875. Compound requests 0.0 to 0.8, context resolution 0.33 to 1.0.

---

## D17. Cloud CLU breaks the on-premise claim, and that is recorded per turn
*Applied.*

The synopsis argues a bank can run this inside its own perimeter. A hosted
CLU provider breaks that for the turns that reach it. `leaves_machine` is part
of the provider contract, the capability registry says it on the dashboard,
and every affected turn carries `data_left_the_machine: true` in its trace.
The `ollama` provider is implemented for a deployment that cannot accept this.

---

## D18. Voice-first UI deferred
*Applied, this round.*

**Context.** Change Request 02 reframes the project as voice-first and R7
rebuilds the customer console as a phone call.

**Choice.** R7 is deferred at the user's instruction: the current interface
is adequate and the priority is improving the substance first. R3's
server-side call state machine, one-turn-at-a-time enforcement and barge-in
cancellation are still in scope, because the double-voice bug and
uncancellable replies are correctness faults that exist on the current UI
too. Minimal Stop and End controls will be added without redesigning the
interface.

**Revisit when.** R0 to R6 are green.

---

## D19. Graphify ignore list is a privacy control
*Applied, this round.*

`.graphifyignore` excludes recordings, enrolment audio, the database, model
weights, `.env` and the frozen snapshot. Document extraction sends content to
a model, so caller audio and biometric embeddings must never enter the
indexing path. Also excluded: graphify's own skill documentation (it would
make the graph about the tool rather than the bank), generated figures (their
source script is already indexed), and the task and prompt files (they are
instructions to the assistant, not descriptions of the system).
