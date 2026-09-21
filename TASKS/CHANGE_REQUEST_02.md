# Change Request 02: Make it a phone call

Read this whole document before changing anything. It builds on `CLAUDE_CODE_PROMPT.md` and `docs/ARCHITECTURE.md`. Where this document conflicts with either, this document wins, and you record the conflict in `docs/DECISIONS.md`.

## The reframe

This is a **voice-first** application. Picture a customer phoning their bank's helpline and this assistant answering. Text is a fallback for a broken microphone, nothing more. Every change below should be judged by one question: does a caller on the line experience this as a natural phone conversation with a competent, honest bank assistant?

Everything built so far stays. The ledger, the risk engine, the capability registry, the compliance trace and the ten beats are the foundation. This round is about the experience of the call and the gaps a real user found.

## Ground rules for this round

1. **Measure before and after.** Every change that claims an improvement (latency, realism, escalation rate) reports a before number and an after number in `docs/RESULTS.md`.
2. **Test the UI in a real browser.** Last round, the UI was only type-checked because the browser extension was not connected, and the dashboard lookup turned out not to work. That cannot happen again. Install Playwright and drive both the customer and compliance UIs headlessly. For the voice path, launch Chromium with `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<file.wav>` so real audio files flow through the real microphone path. A UI change is not done until a Playwright test exercises it.
3. **Keep the honesty registry honest.** New components get registered as `REAL`, `BASELINE` or `SIMULATED`. Cloud components additionally carry `external: true` and a note saying what data leaves the machine.
4. **Offline must still work.** Cloud providers are now welcome, but if the API key is missing or the network is down (review-room WiFi), the system falls back to the local stack automatically and says so in the dashboard.
5. **No em dashes** in any user-facing string, spoken text, comment or doc.

---

## R0. Graphify: give the project a memory (do this first)

Graphify builds a persistent knowledge graph of the codebase and docs so future sessions start from the graph instead of re-reading every file. Repo: https://github.com/Graphify-Labs/graphify

Install and build:

```bash
uv tool install graphifyy          # PyPI name has two y's; or: pipx install graphifyy
graphify install --project         # registers the /graphify skill for this project
```

Then in this Claude Code session run `/graphify .`

Before the first build, create `.graphifyignore` (gitignore syntax). This matters for privacy, because document extraction sends content to the model:

```
.venv/
node_modules/
frontend/dist/
models/
data/recordings/
data/eval/audio/
*.db
*.sqlite*
*.wav
*.webm
.env
secrets/
graphify-out/
```

Then:

- Commit `graphify-out/` (`graph.json`, `GRAPH_REPORT.md`, `graph.html`).
- Run `graphify hook install` so the graph refreshes on commit. At the end of this round run `/graphify . --update`.
- Verify the hook's reminder actually reaches you. There is a known issue where the PreToolUse hook echoes plain text, which Claude Code does not inject into context; it must emit JSON with `hookSpecificOutput.additionalContext`. Check `.claude/settings.json` and fix it if needed.
- Consider `graphify install --project --strict`. Tell me whether you used it and why.

**The graph remembers structure, not decisions.** So also create:

- `CLAUDE.md` at the repo root: how to run, test and demo; conventions; "read `graphify-out/GRAPH_REPORT.md` before searching raw files"; where each subsystem lives; the hard rules (no em dashes, honesty registry, never automate tier 3 resolution).
- `docs/DECISIONS.md`: a numbered decision log. Migrate C1 to C9 from `ARCHITECTURE.md` §5 into it, including the risk formula change (C9) and the tamper localisation complexity correction (C8). Every decision in this round gets an entry: context, options, choice, why.

**Accept:** `graphify-out/GRAPH_REPORT.md` exists and names the ledger, trace, pipeline and risk engine as major components; `CLAUDE.md` and `DECISIONS.md` exist; a new commit refreshes the graph.

---

## R1. Persistence: customers, voices, recordings, calls

**Problem:** enrolling a real voice saves nothing. Restart the server and the customer is gone.

Use SQLite in WAL mode with SQLModel plus **Alembic migrations**. Keep the schema portable so PostgreSQL can replace SQLite later through `docker-compose` without code changes.

Tables, at minimum:

| Table | Key fields |
|---|---|
| `customers` | id, display name, masked registered mobile, created_at, status |
| `voice_enrollments` | customer_id, encrypted embedding, model_id, n_clips, quality score, consent_ref, created_at, revoked_at |
| `calls` | id, customer_id (nullable until identified), started_at, ended_at, language, channel, final_state |
| `turns` | call_id, turn_id, trace_id, state, decision, interrupted flag |
| `recordings` | id, call_id, turn_id, speaker (customer, assistant, agent), encrypted file path, sha256, duration, language, consent_ref, retention_until |
| `cases` | id, call_id, customer_id, reason, status, intake answers, assigned agent, outcome |
| `agents` | id, name, role |
| `access_log` | who viewed or played what, and when |

**This changes an earlier rule, deliberately.** The original spec said raw audio is dropped after transcription. Real bank helplines do record calls, so the new rule is:

- Recording starts only after the greeting's recording notice. If the caller declines or withdraws consent, nothing is stored and existing recordings for that call are purged, with a purge record appended to the ledger.
- Every recording is encrypted at rest (AES-256-GCM). Keys come from a keyfile or `.env`, never the repo.
- Retention window is configurable, default 90 days, enforced by a purge job.
- Only `compliance_officer` can play recordings, and every playback is appended to the ledger as an access event.
- Voice enrolment is biometric data. Store the embedding. Store the enrolment audio only with explicit consent, encrypted, in a separate location.
- Replace the old test "no raw audio on disk" with two tests: "no unencrypted audio on disk" and "no audio stored without consent".

Enrolment flow: a registration page creates the customer, records three clips, stores the enrolment, and confirms. During a call, the caller identifies by stating their registered mobile number or customer ID (demo drawer shortcut allowed), then passive voice verification runs against the stored enrolment.

**Accept:** create a customer, enrol, restart the backend, call in, and get verified against the stored voice. Covered by a test.

---

## R2. Fix the compliance dashboard lookup

**Problem:** the dashboard has fields to enter a session ID and customer ID, and they do not work.

First **reproduce and root-cause** it. Write the cause into `DECISIONS.md` before fixing. My suspicion: sessions were never linked to persistent customers, so customer lookup had nothing to find. R1 should make that possible. But confirm; do not assume.

Required behaviour:

- Search by call/session ID (partial match allowed), customer ID, or case ID. Also a "recent calls" list so nobody has to paste UUIDs during a demo.
- Filters: date range, decision (automated, clarified, refused, escalated, interrupted), risk tier, language.
- Drill into a call: turn-by-turn timeline, each `ComplianceTrace`, risk components, retrieval citations, authentication outcome, redacted transcript, recordings with a player (compliance role only), linked case and its outcome, and the ledger records for that call with per-record verification status.
- Every search and every playback by an officer is itself written to `access_log` and the ledger. Watching the watchers is part of the compliance story.

API sketch: `GET /calls?customer_id=&from=&to=&decision=&tier=&lang=`, `GET /calls/{id}`, `GET /customers/{id}`, `GET /customers/{id}/calls`, `GET /cases?status=`, `GET /recordings/{id}` (streams decrypted audio, compliance only, logged).

**Accept:** a Playwright test logs in as `compliance_officer`, finds a seeded customer by ID, opens a call, sees the trace, plays a recording, and runs ledger verification. A second test proves a `customer` token cannot reach any of it.

---

## R3. The call: one turn at a time, interruptible

**Problems:** there is no way to stop the assistant once it starts speaking. The caller can speak again before the reply finishes, producing two overlapping voices and two replies.

Implement a **server-authoritative call state machine**:

```
CONNECTING -> GREETING -> LISTENING -> PROCESSING -> SPEAKING -> LISTENING ...
                                   \-> HOLD (escalated) -> AGENT
any state -> ENDED
```

Rules:

- **Exactly one active turn per call.** Each turn gets a monotonically increasing `turn_id`. The client plays only audio tagged with the current `turn_id` and discards anything stale. This alone kills the double-voice bug.
- **New speech during PROCESSING** cancels the in-flight turn (asyncio task cancellation, cancel token checked by every stage). The cancelled turn is logged with decision `superseded`.
- **Barge-in during SPEAKING:** the client stops playback within 150 ms, flushes its audio buffer and sends `interrupt`. The server cancels TTS generation and closes the provider stream (some providers, including Sarvam, have no in-band cancel; closing the socket is the cancel). Log how much of the reply was actually played (time offset and text offset), then move to LISTENING.
- **Barge-in detection:** client-side VAD on the microphone, with `getUserMedia` constraints `echoCancellation`, `noiseSuppression` and `autoGainControl` all on. Require roughly 250 to 300 ms of sustained speech before treating it as barge-in, so a cough or the assistant's own echo does not trigger it. Recommend a headset in the runbook.
- **Stop controls** in the UI: "Stop speaking" (interrupt only) and "End call" (hang up). Both work in every state.

Safety rules for interruption, because this is a bank:

- Banking actions commit only after explicit confirmation, atomically, **before** the success message is spoken. If the caller interrupts after commit, the action stands and the next turn says so. If they interrupt a tier 2 read-back, that counts as not confirmed: no action, ask again.
- If the consent or recording notice is interrupted, recording does not start until the notice has been completed or consent given explicitly.

**Accept:** Playwright plus fake-mic tests showing: two rapid utterances produce exactly one reply stream; barge-in stops audio within 150 ms of detection; an interrupted read-back executes nothing; end call works from every state.

---

## R4. Latency: it must feel like a conversation

**Problem:** the gap between the caller finishing and the assistant replying is too long (last measured full round trip 4.6 s).

**Measure first.** Instrument and report p50 and p95 for each stage: endpoint detection, ASR finalisation, NLU, risk, retrieval, TTS time to first byte, network, browser playback start. Put the breakdown in `RESULTS.md` before touching anything.

**The metric that matters** is *end of caller speech to first audible reply*. Report two versions honestly:

- time to first audio (may be a short acknowledgement), and
- time to first **content** audio (the actual answer).

Fillers must not be used to game the first number.

Targets on the demo laptop: first audio p50 under 800 ms; first content audio p50 under 1.2 s and p95 under 2.0 s with cloud TTS; offline path p50 under 1.8 s. If a target is not reachable, say which stage blocks it and why.

Techniques, roughly in order of expected payoff:

1. **Stream the reply audio.** Split the reply into sentences, synthesise the first sentence first, stream audio chunks over the WebSocket, and play them in the browser through a Web Audio queue (AudioWorklet) as they arrive. Never wait for the full reply audio.
2. **Stream recognition.** Transcribe while the caller is speaking (sliding window with local-agreement stabilisation, or a streaming STT provider), so only the last fraction remains at endpoint.
3. **Tune endpointing.** Silence threshold around 500 to 700 ms, shortened when the partial transcript already looks like a complete request. Measure false cut-offs; a too-eager endpoint that interrupts callers is worse than a slow one.
4. **Keep everything warm.** No model loads inside a turn (last round found a 3.7 s cold load in-turn). Preload at startup, warm with a dummy inference, keep provider sockets open per call.
5. **Cache fixed prompts.** Greeting, recording notice, OTP prompt, hold messages, handover lines, apologies: pre-synthesise per language and voice at startup, cache keyed by provider, voice, language and text hash.
6. **Honest acknowledgements.** When a turn needs a lookup, the assistant may say a short neutral acknowledgement ("Let me check that") while retrieval runs. It must never pre-commit to an outcome ("Sure, done") before the decision is made.

**Accept:** before/after latency table in `RESULTS.md`, measured over at least 30 turns per language path.

---

## R5. A voice that sounds like a person on a helpline

**Problems:** the voice is robotic, pronunciations are wrong, and delivery is too uniform.

### Providers

Create `TTSProvider` and `STTProvider` interfaces (`stream(...)`, `cancel()`, `health()`), selectable per language in config, with automatic fallback to the local stack on missing key, error, or time to first byte above a threshold.

- **Sarvam AI (Bulbul v3 TTS, Saaras/Saarika STT):** recommended primary for Hindi, Marathi, Indian English and code-mixed speech. Built for Indian languages, handles Hinglish at the model level, pronounces Indian names and places correctly, supports streaming. Check Sarvam's per-language speaker recommendations and pick the voice per language accordingly.
- **ElevenLabs (Flash v2.5):** option for English where raw speed matters most. Its ~75 ms figure is model inference only; measure real end-to-end time from here, do not quote the vendor number.
- **Piper + faster-whisper:** the always-available offline fallback. Keep them.

Run the eval set through each STT provider and report WER and entity-level error rate per language. Last round, the Hindi, Marathi and code-mixed rows were near 1.0 because of the synthetic audio method. This round, add human-recorded eval audio (the team will record it; prepare the scripts in `data/eval/scripts/` and a small recording page) and report real numbers.

A note from me: "WhisperFlow" was mentioned. If that means Wispr Flow, it is a desktop dictation app, not something to embed. If it means streaming Whisper, R4 item 2 covers it.

API keys live in `.env` only, with `.env.example` documenting them. Add a usage counter to the dashboard (characters synthesised, audio seconds transcribed) because these APIs bill per use. Register both providers as `external: true` with a note that caller audio and text leave the machine when they are active.

### Pronunciation: a spoken-text normaliser

Most "wrong pronunciation" in banking comes from numbers and codes, not the voice model. Build a normaliser that runs before TTS, per language, with unit tests of the exact expected spoken string:

- Rupee amounts in the Indian system: `Rs. 1,50,000` becomes "one lakh fifty thousand rupees" (and the Hindi and Marathi equivalents).
- Masked account and card numbers read digit by digit in small groups: "ending in four three two one".
- IFSC and reference codes letter by letter; OTPs digit by digit with short pauses.
- Percentages, dates, times, phone numbers.
- A lexicon for banking terms: which are spelled out (KYC, EMI, NEFT, UPI, IFSC) and which are words.
- Indian names and places pass through untouched when the provider handles them natively.

### Variation

- Three to five phrasings per response type, rotated so the same phrasing never repeats twice in a row.
- Small per-turn variation in pace and stability, within bounds that stay clear.
- Sentence-level chunks with natural pauses rather than one long uniform stream.

### Fillers ("umm", "achha"): yes, with rules

Light human touches are welcome, under strict control:

- **Allowed:** short thinking or acknowledgement fillers in conversational glue, for example "Hmm, let me check that for you", "Achha, ek second", "Right".
- **Rate-limited:** at most one filler per turn, in roughly a third of eligible turns, never in consecutive turns.
- **Forbidden:** inside amounts, account or card digits, OTPs, read-back confirmations, legal or consent notices, refusal explanations, and any tier 2 or tier 3 turn. Security-critical speech is always crisp.

**Natural is fine; pretending to be human is not.** The greeting states that this is the bank's virtual assistant. If a caller asks whether they are talking to a person, the assistant says it is an automated assistant and offers a human. This is the same trust and transparency problem the paper is about, and it belongs in tests.

**Accept:** normaliser unit tests per language; filler policy tests (never inside digits, never in tier 2 or 3); a short blind listening check where the team compares old and new voices, results noted in `RESULTS.md`.

---

## R6. What the assistant does after it escalates

**Problem:** escalation hands off, and then the assistant has no role. A real helpline does not go silent when it transfers you.

### First: escalate less, clarify more

Add a fourth decision type, **clarify**, between automate and escalate. Ambiguous or compound requests (beat 4 currently escalates at 0.331 against the threshold) should get a short clarifying question, or be split into their parts and handled in order: "I can tell you your balance and your last three transactions. Balance first: ..."

Escalate only on: tier 3 hard overrides, genuine risk, explicit request for a person, or two failed clarifications in a row. Report escalation rate per intent before and after, and tell me if the system was over-escalating.

### Then: the escalated call

When a call is escalated, the assistant stays on the line and does useful, safe work:

1. **Explain plainly.** Tell the caller they are being transferred to a specialist and why, in plain words with no internal scores. Give a case reference number, read digit by digit, and an expected wait.
2. **Protective actions, only.** Offer a small whitelist of reversible, harm-reducing actions, for example a temporary card freeze during a fraud report, each with explicit yes confirmation and a ledger record. Never automate resolution actions: refunds, reversals, transfers, dispute outcomes. This refines the tier 3 rule (tier 3 forbids automating resolution, not reducing harm). Put the whitelist in config behind a flag and record it in `DECISIONS.md` for my sign-off.
3. **Structured intake while waiting.** Ask scripted questions matched to the escalation reason (fraud: when was it noticed, amount, merchant, is the card still with you) and add the answers to the context packet, so the human agent never re-asks.
4. **Hold behaviour.** Periodic brief updates, the option to request a callback instead of waiting, and the ratchet still applies: while on hold, the assistant handles only hold-related questions and whitelisted protective actions.
5. **Agent console at `/agent`.** A queue of escalated calls. The agent accepts a call and sees the context packet (plain-language summary, intake answers, risk components, redacted transcript, links to traces). The agent replies by typing, and the text is spoken to the caller in the caller's language through the same TTS pipeline (normaliser and filler rules included). Live audio relay between agent and caller is a stretch goal. The agent records the case outcome; everything goes to the ledger.
6. **No agent available.** Create the case, offer a callback slot, give the reference number, end the call politely. Any SMS confirmation is `SIMULATED`.

For the demo, a second laptop or browser tab plays the agent. Update beat 7 in `DEMO_RUNBOOK.md`.

**Accept:** a scenario test runs a fraud report end to end: escalation, reference number spoken, card freeze offered and confirmed, intake answered, agent accepts in `/agent`, agent reply spoken to the caller, case closed, all ledger records present and chain valid.

---

## R7. Voice-first customer experience

Rebuild the customer console as a phone call:

- A single prominent "Call DemoBank" button. On connect, the greeting plays automatically: bank name, "virtual assistant", recording notice, and the languages the caller can use.
- **Open microphone for the whole call.** No push-to-talk.
- Clear state indicator (listening, thinking, speaking, on hold) and a call timer. Small optional live captions.
- Controls: mute, stop speaking, end call.
- Language auto-detected from the first utterance; replies match it; switching mid-call works.
- Silence handling: gentle reprompt after about 7 seconds, polite goodbye after two reprompts.
- Text input moves into a collapsed "Microphone not working?" drawer. Still fully functional, since it is the demo's insurance policy.
- A synthetic-data banner remains visible.

Stretch goal only: a real phone number through a telephony provider (Twilio or Exotel, 8 kHz mu-law). Not this round unless everything else is green.

**Accept:** a Playwright test with fake-mic audio places a call, hears the greeting, asks a balance question in Hindi, barges in once, and ends the call. The resulting call appears in the compliance dashboard with its recording.

---

## Order of work

1. **R0** Graphify, `CLAUDE.md`, `DECISIONS.md`
2. **R1** Persistence
3. **R2** Dashboard lookup, with the Playwright harness
4. **R3** Call state machine, interruption, stop controls
5. **R7** Voice-first call UI (built on R3)
6. **R4** Latency (measure first)
7. **R5** Voice realism and providers
8. **R6** Clarify path, escalation experience, agent console
9. **Wrap-up:** all 176 existing tests plus the new ones green, the ten beats updated to the call model, `RESULTS.md` with before/after numbers, `DEMO_RUNBOOK.md` rewritten for a call-based demo, `/graphify . --update`, `DECISIONS.md` complete.

Do not start a phase until the previous one's acceptance tests pass.

## Ask me before you

- Need API keys (Sarvam, ElevenLabs). Build and test with the local stack first; tell me when a key would unlock the next step.
- Enable any protective action in the R6 whitelist beyond a temporary card freeze.
- Change the retention window default or anything about consent wording.
- Change the risk formula or tier cut-points again.
- Drop or weaken any existing test.

When you finish, give me a short summary: what changed, before/after numbers, what you could not do, and every decision waiting for my sign-off.
