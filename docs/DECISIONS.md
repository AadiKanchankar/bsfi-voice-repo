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

---

## D20. SQLModel and Alembic replace hand-written SQL DDL
*Applied, this round. Reverses an earlier choice.*

**Context.** The original build kept the schema as one `SCHEMA` string in
`db.py`, executed with `CREATE TABLE IF NOT EXISTS` on startup. That was the
right call for a system with one table shape and no history. R1 adds eight
tables to an existing database that already holds ledger records, and the
ledger is a hash chain: dropping and recreating it destroys the evidence the
project is about.

**Choice.** `backend/app/models.py` is now the schema, as SQLModel classes,
and `backend/alembic/` holds the migrations. `db.migrate()` runs on first
connection to any database URL and is cached per URL. The `SCHEMA` string is
gone. Plain `sqlite3` connections are still what the pipeline uses; SQLModel
sessions are available through `db.session()` for anything that wants them.
The two are two doors onto one file.

**Consequence, and the trap inside it.** SQLModel's `default=` is applied in
Python when the object is constructed. It does not become a DDL default. Most
of this pipeline writes plain SQL, so an `INSERT` that omits a column with a
Python-side default hits `NOT NULL`. Every defaulted column therefore carries
a `server_default` as well, through the `srv()` helper in `models.py`. This
cost an afternoon and will cost another one if the helper is ever dropped.

**The second trap: the migration connection needed the pragmas too.**
`db.connect()` sets `journal_mode=WAL` and `synchronous=NORMAL`, but Alembic
opens its own engine, and that one ran in rollback-journal mode with
`synchronous=FULL`. Every `CREATE TABLE` then waits on an fsync. On a busy
ext4 journal that is roughly half a second each, and this schema has two
dozen tables, so a test suite that migrates a fresh database per test went
from a quarter of a second per test to twenty. `alembic/env.py` now applies
the same pragmas. The symptom looked like a hang, not a slow migration, which
is why it cost an hour to find.

**Why not PostgreSQL now.** Nothing in the schema is SQLite specific, and the
migrations are portable, so the swap is a URL change plus a `docker-compose`
service. Running the review demo off a local file with no daemon is worth
more than the portability being already exercised.

---

## D21. Call audio is recorded and kept, reversing the drop-after-transcription rule
*Applied, this round. Reverses an earlier choice. Approved by the user.*

**Context.** The original spec dropped raw audio immediately after
transcription and a test asserted "no raw audio on disk". That is a stronger
privacy position than real bank helplines take, and it makes two of the
project's own claims untestable: a compliance officer cannot audit what was
actually said, and a disputed verification cannot be reviewed.

**Choice.** Recordings are kept, under conditions that are enforced in code
rather than promised in a document:

- Storage is refused until the spoken recording notice has completed and the
  caller has consented. `recordings.store()` raises `ConsentError` otherwise.
  Recording by omission is impossible: both flags default to false.
- Everything is AES-256-GCM encrypted at rest, with the call id as additional
  authenticated data, so a file cannot be moved between calls undetected.
- Declining or withdrawing consent purges the call's existing audio and
  appends a purge record to the ledger. Declining is not merely "we stop from
  here".
- Retention is 90 days by default, enforced by `purge_expired()`.
- Only `compliance_officer` and `admin` can play a recording. Every playback
  writes an `access_log` row and a ledger entry.
- Enrolment audio is biometric data and is held separately. The embedding is
  always stored; the audio only on separate explicit consent.

**The digest is of the plaintext, deliberately.** A ciphertext digest would
only prove the file was not edited on disk. A plaintext digest lets an auditor
confirm that what they heard is what was recorded, which is the question that
actually gets asked.

**Test change.** The old "no raw audio on disk" test is replaced by two:
`test_no_unencrypted_audio_on_disk` and
`test_audio_is_not_stored_without_consent`. The second is the one that matters:
the first would pass on a system that recorded everyone without asking.

**Revisit when.** A deployment has a retention rule of its own.

---

## D22. Why the compliance dashboard lookup found nothing
*Root cause, reproduced before any fix. R2.*

**Reproduction.** Against a freshly started backend with a seeded database
holding 25 traces across five sessions, as `compliance_officer`:

| Input | Result |
| --- | --- |
| `3f30d1aa-fd78-4654-b78a-497fc02a79c3` (exact) | 200, 16 traces |
| `3f30d1aa` (what the console displays) | 200, 0 traces |
| `CUST1000` | 200, 0 traces |
| `nonsense-id` | 200, 0 traces |

**Cause, and it is not what it looked like.** `GET /session/{id}/traces` is a
single `SELECT ... WHERE session_id = ?`. It is correct and it works. The
failure is in everything around it:

1. **Nothing can fail.** An unknown session, a typo, a partial id and a
   customer id all return `200 {"traces": []}`, which is byte for byte what a
   real session with no turns returns. The dashboard renders a blank pane and
   no error, so every wrong input looks like an empty call. This alone is
   what "the fields do not work" means to someone using it.
2. **Exact full UUID only.** The customer console displays
   `session {sessionId.slice(0, 8)}`, eight characters. Typing exactly what
   the screen shows returns nothing. The full 36 character value is never
   displayed anywhere, so during a demo there is nothing to copy.
3. **There is one field, and it is session only.** No customer lookup exists
   in `Compliance.tsx` to be broken. The customer field remembered from the
   demo is the picker on the customer console, which is a different screen.

**The suspicion in the change request was right about the gap and wrong about
the symptom.** Sessions genuinely were not linked to persistent customers,
and R1 fixed that with `calls.customer_id` and `sessions.call_id`. But that
linkage was not what made the lookup fail, because customer lookup was never
wired up at all. Recording the distinction matters: fixing only the linkage
would have left the dashboard behaving exactly as before.

**Consequence for the fix.** A lookup that cannot report failure is the
defect, so the fix is not only "add a customer field". Unknown identifiers
return 404 with what was searched for and what kinds of identifier are
accepted; partial ids match by prefix; a recent-calls list means nobody has
to type an identifier during a demo at all.

---

## D23. The seed wrote unmasked mobile numbers
*Found while fixing R2. Applied.*

R1 established that only the last four digits of a registered mobile are
stored: `registry.create_customer` writes `XXXXXX2345`. The seed script did
not go through it and wrote the full ten digits straight into the same
column. Two paths into one column with different rules, and the visible
symptom was that a mobile lookup never matched a seeded customer, because
`find_by_mobile` compares against the masked form.

`scripts/seed_data.py` now masks on the way in. The presenter's stated number
moved to `config.PRESENTER_MOBILE` so the runbook and the seed cannot disagree
about what to say out loud.

Nothing was leaked: every one of those numbers was generated by the seed and
belongs to nobody. The point is that the rule has to hold on every write path,
not on the one that happens to be tested.

---

## D24. BFSI_DB_URL pointed the migrations and the reads at different files
*Found by the first end-to-end run. Applied.*

`db_url()` claims that one setting decides where the data lives. It did not.
`BFSI_DB_URL` was read by the Alembic migration and by the SQLModel engine,
but the raw `sqlite3` connections went through `config.DB_PATH`, which only
ever looked at `BFSI_DB` and the default runtime path. Since almost the whole
pipeline uses raw connections, setting `BFSI_DB_URL` migrated one file and
then read and wrote another.

The browser test is what caught it. It brings up a backend against a
throwaway copy of the seeded database so that a test run cannot write into
the database a presenter is about to demonstrate from. It created a call in
the copy, and the dashboard listed the six calls from the real database
instead. Every unit test had passed, because none of them set `BFSI_DB_URL`:
they pass an explicit path, which always worked.

`DB_PATH` now derives from `BFSI_DB_URL` when that names a SQLite file, and
falls back to `BFSI_DB` and then the default. A PostgreSQL URL leaves
`DB_PATH` at its default, which is correct: the raw sqlite3 path is unused in
that configuration.

**The general point.** Two doors onto one file is a good arrangement only for
as long as both doors are locked to the same file. A configuration switch
that half the code honours is worse than one nothing honours, because the
half that works makes it look configured.

---

## D25. The call state machine is server-authoritative
*Applied, this round. R3.*

**Context.** Two faults were reported from the recorded demo: the caller
could speak again before the reply had finished, producing two overlapping
voices and two replies, and once the assistant started speaking there was no
way to stop it.

**They are one fault.** The client was deciding when a turn began and ended.
A browser that is already playing audio cannot arbitrate that, because it
does not know what the server is halfway through. Adding a mutex in the
browser would have hidden the symptom on one client and left the server
willing to run two turns for one call.

**Choice.** `backend/app/call.py` owns the state:

    CONNECTING -> GREETING -> LISTENING -> PROCESSING -> SPEAKING -> LISTENING
                                       \-> HOLD -> AGENT
    any state  -> ENDED

`begin_turn` hands out a monotonically increasing `turn_id` and supersedes
any turn in flight. The client plays only audio tagged with the current
`turn_id`. Cancellation is cooperative and checked in `trace.stage`, which is
the single point every stage passes through, so a superseded turn stops at
the next stage boundary rather than running to completion and being
discarded. A transition that is not in the table raises.

**Barge-in records what was heard, not what was sent.** `interrupt` takes
`played_ms` and `played_chars` and stores the fraction delivered. A reply the
caller cut off after four words was not delivered, and an audit that records
it as delivered is wrong about what the caller was told.

**Two bugs the tests found, both worth naming.**

*Forgetting an ended call made "ended" unenforceable.* `end_call` dropped the
in-process record, and `get` recreates a missing call in CONNECTING, so a
late or replayed request silently opened a new call instead of being refused.
The ENDED record is a few dozen bytes and it is the only thing that makes the
refusal possible, so it is kept.

*`INSERT OR REPLACE` in `finalise` erased the interrupted flag.* A barge-in
marks the turn interrupted while it is still running; the row written at the
end of the turn then replaced it and set the flag back to zero. Both writes
are now upserts, and `interrupted` is only ever raised, never lowered.

**A call opens in GREETING, not CONNECTING.** The consent notice is the
greeting, so the state says so from the moment the call opens, and completing
the notice hands the floor to the caller. Leaving calls in CONNECTING meant
nothing moved the state until the first turn, so a caller who pressed Stop
during the notice was interrupting a state the server did not believe it was
in. The browser test caught this too: the console printed CONNECTING
indefinitely because it had assumed the state instead of reading it back,
which is the exact habit this phase exists to remove.

**Ending a call used to hide the conversation.** `endCall` cleared the
session id, and the conversation panel was rendered only when a session was
open, so hanging up threw away the transcript the presenter had just produced
and the goodbye was never shown at all. The panel now survives the call and
says "call ended"; the input is disabled rather than removed. Another one the
browser test caught and no unit test could.

---

## D26. An interrupted read-back is not a confirmation
*Applied, this round. Safety rule, R3.*

**The hole.** A tier 2 transaction executes only after the caller has heard
the amount and the payee read back and said yes. Interrupting left the
pending transaction alive in the session state. So: the caller cuts off the
read-back, never hears the amount, says "yes" a moment later meaning
something else, and the transfer executes. The confirmation would have been
consent to something they were never told.

**Choice.** `call.interrupt` calls `turn.drop_pending_for_call`, which
clears any half-finished confirmation on every session of that call and
reports what it dropped. The caller is told plainly that nothing was
confirmed and nothing changed, and the transaction has to be asked for again.
This is the change request's rule stated as code: an interrupted read-back
counts as not confirmed, no action, ask again.

**The other half of the rule holds already.** Actions commit before the
success message is spoken, so interrupting the reply cannot undo a transfer
that already happened. The money moved; the caller simply did not hear us say
so. Both directions are covered by tests, because either one alone would be a
bank losing track of whether something occurred.

---

## D27. A refused action after a passed read-back was recorded as automated
*Found while testing R3. Applied.*

The tier 2 completion path set `decision = "automated"` before looking at
what the dispatch returned. Passing verification, the one time password and
the spoken read-back means the caller was allowed to ask for the action. It
does not mean the action happened: an unregistered payee or insufficient
funds still refuses at the core banking layer.

So a transfer to a payee who was not on file produced a trace reading
`decision: automated, action_taken: refuse`. The compliance dashboard
filters on `decision`, which means that turn would have been counted as an
automated action when nothing was done, and would not have appeared in a
search for refusals.

`decision` is now taken from the outcome: `refused` when the dispatch
refused or declined, with the reason carried into `decision_reason`,
`automated` otherwise. This was found because a test asserted the balance
changed and it had not; the assertion that money moved was the thing that
caught it, and the earlier version of that test compared the wrong account
and would have passed either way.

---

## D28. A string amount from the model crashed the turn
*Found by the R4 latency harness on live audio. Applied.*

`CLUResult.entities` is typed `dict[str, str | float | int]`, so the model is
free to answer `"amount": "Rs 5,000"`, and it does. That string travelled
intact into `dialogue.norm_amount`, which compares it against zero:

    TypeError: '<=' not supported between instances of 'str' and 'int'

The turn died with a 500 in the middle of a call. Every unit test passed,
because the deterministic slot parser in `slots.py` always produces a float
and no test fed model output into the risk scorer. It took running real audio
through the whole pipeline to reach it.

**Fixed in two places, deliberately.** The CLU boundary coerces the amount to
a number, because model output is untrusted input and that is where untrusted
input gets checked. `norm_amount` also degrades to "no amount known" rather
than raising, because it is the money path and it has several callers; one of
them will eventually be written by someone who has not read this entry.

**An amount that cannot be read as a number is dropped, not guessed at.** A
missing amount makes the assistant ask. A wrong one does not.

**The first version of the fix was worse than the bug.** Stripping
non-numeric characters turned `"-5"` into `5`: a sign flip on a transfer
amount, which is a wrong instruction rather than a missing one. The sign is
now preserved and non-positive amounts are dropped. Noted because it is the
kind of mistake that reads as obviously correct.

---

## D29. Latency: synthesis was 71% of the wait, and the compliance layer was free
*Measured before anything was changed, as the change request requires. R4.*

**The old number was true and useless.** RESULTS.md reported a 26 ms turn
total. That was measured on the text path, where neither speech recognition
nor synthesis runs. It described a system nobody uses.

**Measured on the audio path, 120 turns, 30 per language:**

| Stage | p50 |
| --- | --- |
| speech synthesis | 5023 ms |
| speech recognition | 1261 ms |
| speaker verification | 347 ms |
| CLU, a cloud round trip | 261 ms |
| intent and slots | 46 ms |
| policy retrieval | 41 ms |
| voice activity detection | 28 ms |
| risk, fusion, gate, policy | under 1 ms |
| **end of speech to first audible reply** | **7104 ms** |

Two conclusions, and the second one matters more than the first.

**Synthesis is the bottleneck by a factor of four.** Every technique aimed at
the pipeline would have bought nothing. The change request's own ordering put
streaming the reply audio first, and the measurement says that ordering was
right.

**The compliance machinery is free.** Risk, fusion, the tier gate and the
policy check together cost under a millisecond; add intent and retrieval and
it is under a tenth of a second, about 1% of the turn. The thing this project
exists to demonstrate is not what makes it slow. That is worth stating in the
paper, because "compliance costs latency" is the obvious objection and the
measurement refutes it.

**It is worse than reported, not better.** The change request cites 4.6 s
from the recorded demo; the measured p50 is 7.1 s. No attempt is made here to
explain that away. The measurement synthesises the entire reply before any
audio could play and it ran on a laptop with a development server and a
browser competing for it. The ratio between stages is the reliable part.

**What was changed, and what it bought.** Two things, both aimed squarely at
synthesis:

- Replies are spoken phrase by phrase. A reply is about four phrases, so the
  first is ready in roughly a quarter of the time and the rest is made while
  it plays. This needs no streaming protocol: the client asks for the split,
  then fetches and plays each phrase in order, with a token that drops
  phrases still in flight if the caller interrupts or a newer reply starts.
- Fixed lines (the greeting, the recording notice, the OTP prompt, hold
  messages) are pre-synthesised at startup. The greeting costs about 2.8 s
  the first time and nothing after that, and it is the line every call opens
  with.

**The cache is opt in, and that is a privacy decision rather than a
performance one.** Most replies contain a balance, a payee or a name.
Caching those would leave spoken personal data in memory after the call
ended, so only lines that never vary are marked cacheable.

**The 1.2 s target is not reached and the blocker is named.** With the reply
off the caller's clock, what remains is recognition plus the first phrase.
Recognition can only finish after the caller stops speaking, so removing it
means transcribing while they are still talking. That is a streaming
recogniser, a substantially larger piece of work, and it is the honest next
step rather than something to claim now.

**Both first-audio columns are kept even though they are identical today.**
Nothing is streamed from an acknowledgement and no filler is spoken, so time
to any audio and time to content audio are the same number. They are reported
separately from the start precisely so that adding a filler later cannot be
presented as an improvement, which the change request explicitly forbids.

---

## D30. The CLU could hold a live call for 96 seconds
*Found by the R4 latency harness. Applied.*

The contextual layer retries a 429 with backoff: three retries, a thirty
second cap on each, on top of a twelve second request timeout. That policy is
correct for a batch evaluation, where nobody is waiting and cutting a
rate-limited call short measures the free tier instead of the model. It is
indefensible inside a live call.

Measured on one turn: `clu` stage p50 **325 ms**, max **96,169 ms**. A caller
sat on the line for a minute and a half while an optional understanding layer
waited its turn in a free tier's queue.

**Fix.** `CLU_DEADLINE_S`, default 3 seconds, is a ceiling on the total time
the layer may hold one turn across every retry. When it runs out the turn
continues on the deterministic reading, which is always available and is
authoritative anyway (D16, hard rule 6). The evaluation harness lifts the
deadline for its own run, because there the wait really is free.

**It also corrupted the latency measurement.** The code-mixed path came out
at a 94 second p50 and Marathi at 22 seconds, both of them almost entirely
rate-limit backoff rather than anything this system does. Reporting that as
the system's latency would have been the same error as the first CLU accuracy
evaluation, where 20 of 29 calls hit 429 and the resulting number measured
the quota rather than the model.

So `latency.run` now disables the CLU by default and says so in the output.
The headline figures are the local stack, which is what R4's targets are
about, and the cloud layer's own cost is reported separately rather than
smeared across every percentile.

**The general lesson, twice learned now.** A cloud dependency on a free tier
does not fail, it waits. Anything that measures a system containing one has
to decide explicitly whether it is measuring the system or the queue.

---

## D31. Pronunciation is a text problem, not a voice problem
*Applied, this round. R5.*

The complaint was that the voice sounds wrong. Most of it was not the voice
model. It was the synthesiser reading `150000` in the western grouping,
pronouncing `DEMO0001234` as a word, and running a card's last four digits
together into a single number. A better voice would have said all of that
wrong more pleasantly.

`normalise_for_speech` rewrites the text before any engine sees it: rupee
amounts in the Indian system, IFSC and reference codes character by
character, masked account and card digits in pairs, one time passwords one
digit at a time with pauses. The stored transcript keeps the original; only
the spoken string changes.

**Codes are spelled in Devanagari for Hindi and Marathi.** The code itself is
Latin on screen, but spoken as Latin it goes through the Hindi phonemiser
with English vowels and comes out as noise, so the letter names are the ones
an Indian speaker uses: `डी ई एम ओ`.

**A Unicode trap worth writing down.** The one time password pattern used
`\b` around its Hindi keyword. `ओटीपी` ends in a combining vowel sign, which
Python's `\w` does not count as a word character, so there was no word
boundary and the pattern matched nothing. It worked perfectly in English and
silently did nothing in Hindi, which is the worst shape a bug can take in a
multilingual system: the tests that would have caught it are the ones nobody
writes because the feature "obviously works".

Every case is pinned to an exact expected string, per language, because
"sounds about right" is not something a test can check.

---

## D32. Cloud speech providers sit on top of the local stack, never in place of it
*Applied, this round. R5.*

`TTSProvider` and `STTProvider` give Sarvam, ElevenLabs and the local stack
one interface with `health()`, `stream()` and `cancel()`. Selection is per
language, because the right answer differs: a vendor built for Indian
languages is the better choice for Hindi and Marathi and may not be for
English.

**Three things trigger a fallback, and they are the same decision from a
caller's point of view:** no key, an error, or a first chunk slower than
`TTS_FALLBACK_TTFB_MS`. A caller waiting on a slow vendor is no better off
than one waiting on a broken vendor. The budget is 1500 ms because R4
measured the local first phrase at about 1300 ms, so a cloud call that
cannot beat that is not earning the data it sends.

**Sarvam is registered SIMULATED and will stay that way until it has run.**
The request shape is written from the published API. No key exists in this
repository, so not one call has ever been made. Listing it REAL because the
code exists is exactly the dishonesty the capability registry is there to
prevent, and a reviewer asking "have you actually run this" deserves the
right answer.

**TTS and STT are listed separately for the same vendor.** The text
direction sends the reply, which can contain a balance. The audio direction
sends the caller's voice. Those are different promises to break, so they get
different rows.

**The vendor's latency claim is not repeated as ours.** ElevenLabs quotes
about 75 ms; that is model inference only. RESULTS.md carries the end to end
figure measured here, and the registry note says so explicitly.

**Usage is metered on the dashboard.** These APIs bill per use, and a meter
on screen is better than a meter on an invoice.

---

## D33. Fillers are allowed, under rules that are enforced in code
*Applied, this round. R5.*

A short "let me check that" makes a pause feel intentional rather than
broken. It is also the fastest way to make a system sound like it is
pretending to be a person, so the rules live in one function and are tested
rather than trusted to whoever writes the next reply.

Never in a turn at tier 2 or above. Never in a read-back, a refusal, an
escalation, or a consent or recording notice. Never in any text containing
an amount, an account or card number, or a one time password. Never twice in
a row. At most one per turn, in roughly a third of eligible turns.

The digit rule is the one that matters most in practice: a caller writing
down six digits does not need the assistant sounding thoughtful in the
middle of them. It is checked against the text rather than the tier, because
a balance read out at tier 1 is still digits.

**Natural is fine; pretending to be human is not.** Asked whether it is a
person, the assistant says it is an automated assistant and offers a human,
before any of the styling can hedge it. That is the same trust question this
project is about, so it is answered in the pipeline and pinned by a test
rather than left to a prompt.

---

## D34. The evaluation audio is synthetic, and that invalidates three of its rows
*Stated, not fixed. R5. Needs the team.*

The evaluation clips are rendered with Piper. For English that is a
limitation. For Hindi, Marathi and code-mixed it makes the word error rates
meaningless: a synthesiser transcribing its own output measures the round
trip through two models, not speech recognition.

This cannot be fixed by writing code. It needs people reading the lines
aloud, so what exists now is the apparatus for that:
`data/eval/scripts/{en,hi,mr,mix}.md` with the exact lines, and a `/record`
page that captures them through the same microphone constraints the call
path uses, because the point is to measure what the system will actually
hear rather than what a studio would.

It also fixes a second problem. The latency harness wants 30 distinct clips
per language and has 28, 10, 8 and 8, so it currently cycles them and says
so in RESULTS.md. Real recordings remove that caveat too.

---

## D35. The system was not over-escalating on confidence, and the escalation rate was inflated
*Measured, R6. One finding needs your sign-off.*

The change request asked for the escalation rate per intent before and
after, and whether the system was over-escalating. Measured over the 54
evaluation utterances, with verification refreshed each turn so that
verification expiry could not be mistaken for a confidence problem:

| Outcome | Count | What it is |
| --- | ---: | --- |
| automated | 19 | answered |
| refused | 6 | correctly declined |
| escalated, tier 3 | 11 | fraud, disputes, investment advice: mandatory |
| escalated, awaiting OTP | 14 | **not an escalation at all, see below** |
| escalated, low confidence | 3 | the case `clarify` is for |
| clarify | 1 | asked instead of transferring |

**The answer to the question asked is: no.** Only 4 turns out of 54, under
8%, turn on the confidence check, and those are the only ones `clarify` can
help. The overwhelming majority of escalations are tier 3 hard overrides,
which are mandatory and correct, and would have been unaffected by anything
R6 does.

**But the reported escalation rate was wrong, and that is the real finding.**
Fourteen of the thirty-four "escalations" are tier 2 turns where the
assistant asked for a one time password. No human is involved, no handover
packet is created, and the call continues normally: the caller supplies the
OTP and the transaction proceeds. Labelling that `escalated` inflates the
escalation rate by roughly 40% and makes the dashboard show transfers that
never happened.

**I have not changed the label, deliberately.** It is asserted by
`test_scenarios.py::test_beat_6_...`, and the change request lists altering
an existing test as something to ask about first. The honest metric is
available without the rename: a real escalation is one with a
`handover_packet_ref`, and the OTP turns have none.

**Recommended, for sign-off:** give the OTP and read-back stages their own
decision value, something like `awaiting_input`, rather than overloading
`escalated`. It is the same class of defect as D27, where a refused action
was recorded as automated: the trace said something that was not true, and
the dashboard believed it.

**Why `clarify` is still worth having.** It fires rarely on this evaluation
set because the set is mostly clean single-intent utterances. The case it
exists for is the one from the recording: a compound, code-mixed request
that the single-label head cannot represent and is therefore not confident
about. That is a real caller behaviour that a synthetic evaluation set
under-represents, which is an argument for the human recordings in D34
rather than against the feature.

---

## D36. Protective actions: one, and a written reason for each of the others
*Applied, this round. R6. The whitelist is the sign-off item.*

Tier 3 forbids automating a **resolution**. Reducing harm is a different
thing, and the difference needed writing down rather than arguing per case:
a frozen card can be unfrozen and the fraud is still unresolved; a refund
cannot be unpaid and the dispute is over.

`config.PROTECTIVE_ACTIONS` lists four, and `PROTECTIVE_ACTIONS_ENABLED`
contains exactly one:

- **`freeze_card`, enabled.** Reversible in one step, resolves nothing,
  stops the loss while the caller waits.
- **`lower_daily_limit`, not enabled.** Reversible and harm-reducing, so a
  reasonable candidate, but it changes a limit the caller may rely on within
  the hour. Needs your sign-off.
- **`block_payee`, not enabled.** Same shape. Needs your sign-off.
- **`reverse_transaction`, never.** It resolves the dispute, which is
  exactly what tier 3 forbids. Listed explicitly so nobody adds it later
  believing it was merely overlooked.

Anything not enabled raises `NotWhitelisted` with a message naming what is
enabled and saying that adding one needs a decision entry and sign-off. A
test asserts that every enabled action is reversible, and another asserts
that `reverse_transaction` has no reasons and is marked irreversible, so
enabling it by accident fails the suite.

Nothing runs without an explicit yes. A caller who said "hmm" has not
consented to their card being frozen.

---

## D37. An escalated call is not silence
*Applied, this round. R6.*

Before this, escalation built a handover packet and the assistant had
nothing further to say, which is the worst possible moment to go quiet: the
caller has just reported fraud.

Now it explains in plain words with no scores or tier numbers, gives a case
reference spelled character by character so it can be written down, offers
the one safe protective action, asks the questions the agent would have
asked anyway and attaches the answers to the case, and gives periodic hold
updates with a callback option. If nobody is free it says so, logs the case,
gives the reference and ends politely rather than holding someone for an
agent who is not coming. Any SMS is SIMULATED and the registry says so.

The agent console at `/agent` shows the queue, and accepting a case returns
the intake answers, the risk reasoning and the redacted transcript, so the
caller does not repeat themselves. The agent types and the caller hears it
in their own language through the same normaliser and voice as everything
else, so an amount an agent types is read in the Indian system without the
agent needing to know that. Every step is a ledger record, and the
acceptance test verifies the chain after the whole sequence.

---

## D38. Three turns that are not requests, all answered with the same refusal
*Found in the 21 September recording. Applied.*

Observed in one call, each producing the identical reply:

    "I do not have a verified answer to that, so I am not going to guess.
     The closest thing I have on file was not a close enough match."

- **Silence.** Two turns transcribed as nothing. Trace: `transcript` empty,
  `intent out_of_scope (0.0%)`, `c_final 0.0003`.
- **The voice phrase.** The assistant said "Tap the microphone and say: my
  voice is my password". The caller typed exactly that and it came back
  `out_of_scope (95.0%)`, refused.
- **"Thank you."**

**Every stage behaved correctly.** An empty string has no intent, so the
classifier honestly returned `out_of_scope` at zero confidence, retrieval
honestly found nothing above the floor, and the gate honestly refused on
grounding. The absurdity came from a missing case, not a broken one, which
is why no test caught it: each component was doing its job on an input
nobody had decided what to do with.

`run_turn` now answers these before classification, in
`pipeline/smalltalk.py`. None of them sets an intent, touches a slot or
reaches a banking function, so there is nothing for risk or the gate to
decide. They are recorded as `clarify` rather than `automated`, because the
assistant asked rather than did.

**The first version of this broke the whole tier 2 flow.** An OTP and a
read-back confirmation arrive with no text at all, because the caller
pressed a button rather than said something, so the blank guard classified
them as silence and answered "I did not catch that" instead of checking the
code. Six tests caught it, which is the argument for having them: the guard
now runs only when the turn carries no structured input, and a test pins
that specific case.

**The courtesy matcher is anchored deliberately.** `thanks, now block my
card` is a request, and answering it with "you are welcome" would be a worse
bug than the one being fixed. A test asserts exactly that.

---

## D39. "The card ending on file"
*Found in the 21 September recording. Applied.*

When the last four digits were unknown, the read-back substituted the words
`"on file"` into the phrase "the card ending {x}", producing **"You want me
to permanently block the card ending on file."**

Not English, and on the single most safety-critical sentence the system
speaks: the one a caller says yes to immediately before a card is blocked.
It is now two separate sentences rather than one sentence with a hole in it.

---

## D40. The demo served a new frontend against an old backend
*Found from the 21 September screenshots. Applied.*

Two screenshots, two errors, one cause. `405 Method Not Allowed` on
registration, because the old backend had `GET /customers` but not `POST`.
`404 Not Found` on the dashboard, because `GET /calls` did not exist yet.

`make demo` ran uvicorn without `--reload`, so Vite hot-reloaded the
frontend on every change while the Python process kept serving whatever it
had been started with. Nothing on screen said so, and the failure looks
exactly like a bug in a button.

Two changes. `make demo` now passes `--reload --reload-dir backend`, so it
stops happening. And `/health` returns the list of features this build
supports, which the page checks on load: if the backend is older, a red
banner names the missing features and says to restart. A mismatch that
announces itself is worth more than one that cannot recur, because the
second will find a new way to.

---

## D41. A select in a flex row ate every input beside it
*Found from the 21 September screenshots. Applied.*

The registration form rendered as two empty slivers next to a full width
language dropdown, with the Name and Mobile placeholders invisible.

`input, select { width: 100% }` from the base rule, and `.row > input
{ flex: 1 }`, which is `flex-basis: 0`. In a flex row the inputs therefore
started at zero and grew from what was left, and the select, having no flex
rule at all, kept its 100% basis and left nothing. Both now share
`flex: 1 1 8rem; min-width: 0`.

---

## D42. Pre-synthesising prompts blocked startup for forty seconds
*Regression I introduced in R4. Found on a real restart. Applied.*

D29 moved the fixed prompts off the caller's clock by synthesising them at
startup. They were synthesised inside the FastAPI lifespan, which is
awaited before the server accepts a single connection:

    Started server process
    Waiting for application startup.
    [vite] proxy error /health: ECONNREFUSED    (x20, for forty seconds)
    warmed embeddings in 5.2s
    pre-synthesised 12 fixed prompts in 37.8s

So `make demo` looked dead for the best part of a minute, every browser
request in that window failed, and the page reported "Could not load
customers: Unexpected end of JSON input" because the proxy returned nothing.
D40 had just added `--reload`, which made it worse: every code change now
cost the same forty seconds.

**Warming is an optimisation.** The greeting is faster once it has run and
correct before it has, so it belongs in a background thread, not on the
startup path. `/health` reports `warmup.state` so the page can say the first
reply will be slower rather than leaving it a mystery.

**The banner I added in D40 made this worse, not better.** It reported three
different conditions as one: "the backend is running older code". A backend
that is still starting is not old, and telling someone to restart the thing
that is mid start is the opposite of helpful. It now distinguishes starting,
warming and genuinely stale, polls every two seconds, and clears itself.

**What I should have noticed.** D29 says the point was to take work off the
caller's clock. Moving it onto the startup path took it off one clock and
put it on another, and I did not measure a restart afterwards. The
measurement that would have caught it takes one command.

---

## D43. Recording evaluation audio without being able to hear it back
*Found in use. Applied.*

The `/record` page could capture a clip and mark it done, with no way to
play it. Recording without listening is not reviewing: the one thing a
person needs to check is whether the microphone was picked up at all, and
the page could not answer it. `GET /eval/audio/{id}` serves a stored clip
and each recorded row now has a player.

---

## D44. The test suite was killed by its own cleanup
*Found after two silent failures. Applied.*

Two consecutive full runs died at test 59 with no summary, no traceback and
no failing test: the process simply vanished. Not memory, with 7 GB free and
no OOM kill in the kernel log.

The e2e teardown was signalling a process group it looked up by pid **at
teardown time**:

    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

`proc` is a server that may already have exited. Linux recycles pids. So
this resolves whatever process now holds that number, takes its process
group, and terminates it. Twice that was the pytest run itself, which is
why the suite died mid-flight with nothing written down.

`start_new_session=True` already makes the child a group leader, so its
group id is its pid **at spawn** and needs no lookup at all. The teardown
now uses that, returns early if the process has already exited, and refuses
outright to signal its own group.

**Two things this cost beyond the time.** The first interrupted run left
servers holding 8099 and 5199, so the next run skipped all twelve browser
tests and reported itself green on a partial suite. And I twice reported a
killed run as though the code were at fault.

**The general shape.** A cleanup path that is wrong is worse than one that
is missing, because it runs when everything else has already worked, it
destroys the evidence of what it did, and nobody suspects it.
