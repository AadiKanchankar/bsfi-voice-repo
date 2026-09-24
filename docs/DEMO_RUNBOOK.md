# Demo runbook

Read this the night before the review. It is the script, the recovery
procedures and the answers to the questions the panel will ask.

Total running time for the ten beats is about eight minutes at a normal
speaking pace. Budget ten.

---

## The night before

```
make setup          # once per machine, needs network
make models         # once per machine, needs network, pre-downloads everything
make seed           # synthetic data, intent head, KB index, enrolled voices
make test           # everything must be green
make eval-audio     # renders the evaluation audio
make eval           # regenerates docs/RESULTS.md
```

Then check:

- [ ] `make test` is green, including `backend/tests/test_scenarios.py`, which
      is all ten beats in text form. If that file passes, the demo works even
      if every microphone in the building fails.
- [ ] `docs/RESULTS.md` has today's timestamp and no empty rows.
- [ ] `make verify` prints `"ok": true`.
- [ ] Laptop volume is up and the browser has microphone permission for
      `http://127.0.0.1:5173`.
- [ ] Airplane mode on, then `make demo` again. Nothing should reach the
      network. If something does, `make models` was not run.

Have a second terminal open and ready at the repository root. Beat 10 needs
it.

---

## Starting

```
make demo
```

Backend on `http://127.0.0.1:8000`, frontend on `http://127.0.0.1:5173`.

Open two browser windows side by side:

- left: `http://127.0.0.1:5173/` the customer console
- right: `http://127.0.0.1:5173/compliance` the compliance dashboard

Cold start is about 5 seconds on the development machine, comfortably inside
the 60 second budget. The server warms the embedding model at startup, so the
first turn is no slower than the rest. Send one throwaway question anyway, to
confirm audio output works before the panel walks in.

---

## The script

Say this first, once, before beat 1:

> Every customer, account, card and voice in this demo is synthetic, generated
> by a seed script. There is no real banking system behind it. The banner at
> the top of the screen says so, and the capability registry on the dashboard
> lists exactly which components are real, which are simplified baselines and
> which are simulated.

### Beat 1. Consent

On the customer console, leave the customer as `CUST1000`, leave "attach a
seeded voice clip" ticked, click **Give consent and start**.

> Point at the consent notice. Purpose and retention are stated before any
> audio is processed. This is not a checkbox, it is the first record in the
> audit ledger. It is record zero, before anything else exists.

Switch to the dashboard, **Ledger** tab, show record 0 with kind `consent`.

### Beat 2. Tier 0 in English

Click the **2. Tier 0** button, or type:

> What are your home loan interest rates

Paste the session id into the dashboard, press **Load session**, select the
turn.

> Show the retrieval panel: the document id, the version, the effective date
> and the similarity score. The assistant said the source out loud. Note the
> version is 1.1 and not 1.0: both are in the knowledge base, and the
> superseded one was deliberately excluded.

Tier is 0. No authentication was required and none was performed.

### Beat 3. Refusal

> What is the CEO's personal phone number

> Nothing cleared the similarity floor. The assistant did not improvise, it
> declined and offered a human. The dashboard shows the exact number: the best
> passage scored about 0.1 against a floor of 0.42. There is no generation
> step in this system that could have papered over that.

### Beat 4. Code-mixed

> Mera balance kitna hai, and last three transactions bhi bata do

> The language panel shows per-word spans, not one language for the whole
> call. Hindi, then English, then Hindi, with a code-mix index of about 36.
> Most pipelines run language identification once per call and cannot
> represent this sentence at all. The spans come from Viterbi smoothing with a
> switch penalty, so the tagger reports coherent runs instead of flipping every
> second word.

**Expect this turn to escalate, and say why before anyone asks.** The caller
asked for two different things in one breath, so the intent head splits almost
evenly between `mini_statement` at about 0.33 and `get_balance` at about 0.30.
Confidence fusion turns that into `c_final` of about 0.61 against a tier 1
threshold of 0.62, and the system hands off rather than guessing which half of
the request to answer.

> This is the behaviour we want, not a miss. The assistant understood the
> languages perfectly, and it still declined to act, because it could not tell
> which of two things it was being asked to do. A system that picked one at
> random would look better in a demo and be worse in a bank. The dashboard
> shows the runner-up intent and the margin, so the reason is on screen.

If you would rather show a clean automated answer on a code-mixed sentence,
use a single-intent one instead: "Mera balance kitna hai" on its own.

### Beat 5. Tier 1

> What is my account balance

**Before this beat, press Verify my voice** (or "Use seeded clip" if the
microphone is dead). Account questions do not proceed without a check; that is
the point.

> This one touches an account, so it needs to know who is speaking. The
> dashboard shows the cosine against the enrolled embedding, the anti-spoof
> score, and the product of the two, which is what feeds the risk formula. The
> check is good for five minutes or five turns and then expires, because a
> verification is evidence about who is speaking now, not a permanent property
> of the session. The anti-spoof component is labelled BASELINE on screen
> because it is a classical LFCC and GMM baseline, not a trained AASIST
> countermeasure. We are not going to claim otherwise.

If you pressed "Use seeded clip", say so: that path is labelled SIMULATED on
every turn it carries, because it demonstrates the mechanism rather than
checking a speaker. For a real demonstration, enrol your own voice first and
then verify with the same microphone.

### Beat 6. Tier 2

> Block my card ending 4321

The assistant asks for an OTP. Click **Submit OTP 123456**. It then reads the
action back. Click **Confirm read-back**.

> Blocking a card is irreversible, so it sits at tier 2 whatever the risk
> score says. Verification, a one time password and a spoken read-back, all
> three, before anything commits. The OTP is a fixed demo code and the registry
> marks it SIMULATED. Watch what happens if I decline the read-back instead:
> nothing is done to the account and the decision is recorded as refused.

### Beat 6b. Interrupting the read-back

Ask for the transfer again, and this time click **Stop speaking** while the
read-back is playing, then say yes.

> I cut it off before it told me the amount and the payee. So when I say yes
> a moment later, what am I agreeing to? Nothing, is the answer. The server
> treats an interrupted read-back as not confirmed, drops the pending
> transaction and says so. Watch the balance: it has not moved. The ledger
> records the interruption, including how much of the reply I actually heard
> before I cut it off.

The mirror of it is worth one sentence: if I interrupt *after* confirming,
the transfer stands, because the action commits before the success message is
spoken. The money moved and I simply did not hear us say so. Both directions
are covered by tests, because a bank that is unsure whether something
happened has a worse problem than a slow assistant.

**Stop speaking** and **End call** work in every state. The state is printed
under the session panel and it comes from the server, not the browser: that
is what stops two replies playing over each other.

### Beat 7. Tier 3

> Someone has made a fraudulent transaction on my account

> Hard override. This does not go through the score at all. Fraud reports,
> disputes and explicit agent requests are tier 3 unconditionally, so a bug in
> the risk arithmetic can never automate one. The dashboard shows
> `tier_overridden: true`. Go to the Escalation queue tab and click Claim: the
> agent receives the whole conversation so the customer does not repeat
> themselves, and the packet says explicitly that no automated action was
> taken.

**Then stay on the line.** This is the part that changed: the assistant used
to go quiet here, which is the worst possible moment for it.

> It gives me a case reference, read out digit by digit so I can write it
> down. It offers one thing it is allowed to do while I wait: freeze the
> card. That is reversible and it resolves nothing, which is why it is the
> only action on the whitelist. A refund would resolve the dispute, and
> automating a resolution is exactly what tier 3 forbids, so it is in the
> config file marked never.

Say yes to the freeze, then answer the intake questions it asks.

> It is asking what the agent would have asked anyway: when I noticed, how
> much, whether I still have the card. Those go on the case, so nobody asks
> me twice.

Open `/agent` on the second laptop and click Accept.

> The agent sees the intake answers, the risk reasoning and the redacted
> transcript. Identifiers are tokens, not values: the agent sees what the
> compliance record sees. I type a reply here and the caller hears it in
> their own language, through the same normaliser, so an amount I type is
> read in the Indian system without me having to know that.

Close the case with an outcome.

> Every step of that was a ledger record. Case opened, card frozen, intake
> taken, agent accepted, agent spoke, case closed. Verify the chain and it
> is still green.

Then ask an innocent question:

> What are your home loan interest rates

> Still tier 3 for anything touching the account. The session tier ratchet
> means you cannot lower your own risk by asking something harmless after an
> escalation.

Then ask a public question, "what are your home loan interest rates", and show
that it is answered at tier 0:

> Public information is exempt from the ratchet, and that exemption is not a
> softening of the control. An earlier build had the ratchet with no
> exemption, and one misheard sentence pinned the whole call at tier 3: the
> assistant then refused to quote its own published interest rates for the
> rest of the conversation. The floor now also only moves when the system was
> confident about what it heard, and decays after a few clean turns.

### Beat 8. PII

Type:

> my card is 4539 5787 6362 1486

> The stored transcript shows a token, not the digits. The raw value is in a
> per-session AES-256-GCM vault in a separate table, and the transcript store
> never holds it. The card number was Luhn validated before tokenisation, and
> a twelve digit number that fails the Verhoeff checksum is not mistaken for
> an Aadhaar number. The raw audio was dropped from memory as soon as
> transcription finished, and there is a test asserting no audio file exists
> on disk after a turn.

Optionally click **Withdraw consent and purge** to show erasure, then the
purge record in the ledger.

### Beat 9. Audit

Dashboard, **Ledger** tab, click **Verify Ledger**.

> Green. Every record checked. The chain is SHA-256 over the previous hash,
> the canonical JSON of the record and its timestamp, with an HMAC signature
> under a key that is not stored in the database.

Also click **Try export as customer** to show the role boundary being enforced
live.

### Beat 10. Tamper

In the second terminal:

```
python scripts/tamper_demo.py
```

It prints which record it edited and what it changed. Then, on the dashboard,
click **Verify Ledger** again.

> Red. And it does not just say something is wrong, it names the record: index,
> record id, which of the three checks failed, and the expected hash against
> the actual one. The row is highlighted in the chain below. All I did was a
> plain SQL UPDATE on one field of one stored record. I recomputed nothing,
> because a real attacker with database access would not.

To restore:

```
python scripts/tamper_demo.py --restore
```

---

## Beat 11. Investment questions, and where the assistant stops

Worth adding to the script: it is the clearest demonstration that the system
knows the limit of its own authority.

Ask a factual one first:

> What is my portfolio worth

It answers: six holdings, a total, and the past-performance caveat. Then ask
for advice:

> Which stock should I buy right now

> It refuses, and it says why. Under the SEBI Investment Advisers
> Regulations only a registered adviser may answer that, and this is not one.
> It is tier 3, mandatory handover, and no confidence score can automate it,
> the same class as a fraud report. Note it does not hedge either: a hedged
> recommendation is still a recommendation, and there is a test asserting the
> refusal contains none.

Then ask your balance again, to show the session is not poisoned:

> Asking for advice is not a risk signal, so unlike a fraud report it does
> not raise the session floor. Getting that wrong locked the caller out of
> their own balance for the rest of the call.

### Beat 11b. "Are you a real person?"

Ask it straight out, in the middle of the call.

> It says it is an automated assistant and offers to put me through to a
> colleague. It never claims otherwise, and that answer is produced before
> any of the conversational styling can soften it. This is the same trust
> question the whole project is about, so it is a test rather than a prompt
> we hope holds.

### Beat 11c. What it actually says out loud

Worth pointing at the numbers rather than the voice:

> A balance of one lakh fifty thousand rupees, not one hundred fifty
> thousand. An IFSC read letter by letter, because nobody can write down a
> code pronounced as a word. A card's last four in pairs. An OTP one digit
> at a time. Most of what sounded wrong before was not the voice model, it
> was the text we handed it.

And the rule about fillers, if anyone asks why it says "let me check that":

> At most one per turn, about a third of the time, never twice in a row, and
> never anywhere near digits, money, a read-back, a refusal or a tier 2
> turn. A caller writing down six digits does not need us sounding
> thoughtful in the middle of them.

## Voice settings

All of these are `.env` values, changeable without touching code.

| Setting | Values | Effect |
| --- | --- | --- |
| `BFSI_TTS_GENDER` | `female`, `male` | One setting across every engine and language |
| `BFSI_TTS_ACCENT` | `indian`, `neutral` | Indian English is a Hindi voice on the English phonemiser |
| `BFSI_TTS_PAUSES` | `1`, `0` | Phrase-by-phrase synthesis with real pauses |
| `BFSI_TTS_BREATHS` | `1`, `0` | Occasional inhale before a long sentence |
| `BFSI_TTS_ENGINE` | `auto`, `elevenlabs`, `kokoro`, `piper` | `auto` prefers ElevenLabs if a key is set |

Samples of each combination are in `Testing-photos-Videos/voice-v2/`.

## If something breaks

| Symptom | Do this |
| --- | --- |
| Microphone does nothing | Use the text box. The pipeline after the transcript is identical, and the demo script buttons drive it. Say so out loud: it is a design feature, not a save. |
| Backend will not start | `make clean && make seed && make demo`. `runtime/` is disposable; `data/` is not. |
| "intent head not found" | `make seed` |
| "policy KB index missing" | `make seed` |
| First turn takes 10 seconds | The embedding model is loading. Send one throwaway question before the panel arrives. |
| Ledger already red at beat 9 | `python scripts/tamper_demo.py --restore`. Somebody ran the tamper script and did not restore. |
| Dashboard empty | Paste the session id from the customer console into the dashboard box and press Load session. |
| A voice is missing | `make models`. Replies still come back as text, and the trace is unaffected. |
| Voice sounds robotic | Kokoro did not load, so it fell back to Piper. Check `models/kokoro/` has both files; `GET /capabilities` and the trace's tts stage name the engine actually used. |
| "No voice check has been done in this session" | That is correct behaviour, not a fault. Press Verify my voice. Account questions need a check; it lasts five minutes or five turns. |
| Verification fails on your own voice | Enrol first, from the same microphone. The seeded enrolments are synthetic and band limited; a live recording scores about 0.50 against them. |
| A customer has no seeded clip | Only CUST1000 to CUST1002 have one. For anyone else, enrol a real voice. |
| Everything is broken | `make test` in a terminal. Run `backend/tests/test_scenarios.py -v` on the projector. It performs all ten beats and prints them. It is a worse demo but it is a real one. |

---

## Questions the panel will ask

**"Is the speech recognition actually running, or is that pre-recorded?"**
It is running. `faster-whisper base`, int8, on the CPU of this laptop. The
stage timeline shows the measured milliseconds for every turn. It is not
fine-tuned on banking audio, which the capability registry states and
RESULTS.md repeats.

**"What is your accuracy?"**
Point at RESULTS.md. WER and the entity-level error rate on a 54 utterance
hand-labelled set, with the set size next to every number. Then say the
important part: the evaluation audio is Piper-rendered, not human telephony
audio, so the WER is optimistic. The entity-level error rate is the number
that matters and it is the baseline a fine-tuned model has to beat.

**"Is the anti-spoofing real?"**
It is a real LFCC and GMM baseline, and it is registered BASELINE, not REAL.
It is not AASIST. Both the bona fide and the spoof class in our measurement
come from a TTS system, because no human speech is collected in this build, so
the reported EER and t-DCF characterise two synthesis conditions and not human
speech against deepfakes. That caveat is printed in RESULTS.md next to the
number.

**"Could someone just edit the database?"**
Yes, and that is beat 10. They can edit it, and the chain detects it and names
the record. What they cannot do without the HMAC key is edit it undetectably.

**"Why not an end to end speech model? It would be faster."**
It would, and it emits audio and nothing else. Each stage of this pipeline
emits an artefact a compliance officer can read. That is the trade this
project argues for and the reason the architecture is cascaded.

**"How many languages?"**
Three in this build: English, Hindi and Marathi, including code-mixed
utterances. The synopsis commits to five, and that gap is stated in
ARCHITECTURE.md rather than glossed over. The Viterbi tagger is written for an
arbitrary language set, so adding one is a config entry plus a lexicon.

**"Does it work as well in Hindi and Marathi as in English?"**
No, and the numbers say where it falls down. Retrieval is the problem: the
policy knowledge base is written in English, so a Marathi phrasing of an
answerable question scores a mean top similarity of 0.31 against 0.72 for the
English phrasing, and the single global floor then refuses it. That is a
cross-lingual embedding gap, not a language the system cannot understand, and
it is printed per language in RESULTS.md. The fix is a per-language floor or
translated passages, and neither is in this build.

**"Why does it sound better than the recording we saw?"**
Three changes. The Hindi and Marathi replies were written in romanised Latin
and the speech engine phonemises from script, so it was reading Hindi with
English vowels; they are Devanagari now. The engine is Kokoro-82M rather than
Piper, which is markedly more natural at about a 0.35 real-time factor on this
CPU. And amounts and account digits are spoken as words rather than read off
as database fields.

**"What is simulated?"**
Core banking, OTP delivery and the agent console. All three are listed on the
System tab with the reason. Everything else in the registry is REAL or
BASELINE and labelled accordingly.

---

## Reset between runs

```
make clean && make seed
```

`runtime/` holds the database, the trained head, the KB index and the
calibration. All of it regenerates. Nothing in `data/` is generated at demo
time, so nothing there is at risk.
