# Contextual Language Understanding layer

An optional model that reads a turn before the deterministic pipeline sees
it. Off by default. With `BFSI_CLU_PROVIDER=null`, this system behaves
exactly like the frozen snapshot in `stable-local-2026-09-21/`.

## Why

The deterministic classifier is a logistic head over sentence embeddings,
trained on a fixed bank of utterances. It is fast, auditable and reproducible,
and it cannot represent three things real callers do constantly:

- **Compound requests.** "Mera balance kitna hai aur last three transactions
  bhi bata do" is one utterance with two asks. A single-label classifier has
  to pick one, splits its posterior between them, and then the confidence
  gate refuses the turn because it is unsure. Measured: 0.0 accuracy on
  compound cases.
- **Reference to earlier turns.** "Aur uske pehle wali?" means nothing on its
  own. Every turn is classified independently, so this is noise. Measured:
  0.4 on follow-ups.
- **Code-mixing beyond the seeded lexicon.** Romanised Hindi and Marathi
  outside the function-word list fall through to English.

On a 40-case set built specifically from these, the deterministic classifier
scores **0.65**. That is the number the layer has to beat.

## Where it sits

```
ASR -> language ID -> deterministic NLU -> [CLU] -> retrieval -> risk -> gate -> action
                              |              |
                              |              +-- reads, proposes
                              +-- always runs, is the floor
```

The deterministic head runs on **every** turn whether or not the CLU is
enabled. The CLU proposes; the merge decides; the rest of the pipeline is
untouched.

## What it is not allowed to do

This is the part that matters for a banking system. The CLU has no route to
an action. It cannot authenticate, score risk, authorise, ground an answer,
or move money. It returns structured meaning and nothing else.

On top of that, **it may raise the assessed risk of a turn and never lower
it**:

| Situation | Outcome |
| --- | --- |
| Baseline `get_balance`, CLU says `fraud_report` | CLU wins, turn escalates |
| Baseline `fraud_report` at 0.82, CLU says `product_info` at 0.99 | **refused**, stays `fraud_report` |
| Baseline `fund_transfer` at 0.80, CLU says `product_info` | **refused**, stays `fund_transfer` |
| Baseline `fraud_report` at 0.30, CLU says `mini_statement` at 0.88 | CLU wins, and the relaxation is recorded |

That last row is a carve-out, and it exists because an absolute rule was
worse in testing. The deterministic head fired `fraud_report` at 0.30 on the
harmless follow-up "aur uske pehle wali?", and an unconditional floor pinned
that turn to mandatory handover. A 0.30 posterior is noise, not evidence of
fraud. So a downgrade from a hard-handover intent needs **both** an
unconfident deterministic reading (below `CLU_BASELINE_TRUSTED_ABOVE`, 0.45)
**and** a confident model one (above `CLU_OVERRIDE_NEEDS_CONFIDENCE`, 0.70),
and every occurrence is written into the trace.

Rule-based slots also win over model entities on any key the rules extracted,
because a regular expression is readable in a way model output is not.

## When the model is called

Not on most turns. A confident, monolingual, single-intent request is
something the logistic head already gets right.

| Trigger | Threshold |
| --- | --- |
| Baseline intent confidence low | below `CLU_CALL_BELOW_CONFIDENCE`, 0.70 |
| Top two intents close together | within `CLU_CALL_BELOW_MARGIN`, 0.15 |
| Utterance is code-mixed | code-mix index above 0 |
| Short utterance referring to an earlier turn | 8 words or fewer, plus a reference word |

Conversation context is bounded at `CLU_CONTEXT_TURNS` (4) redacted turns.
Unbounded history would be a cost problem and, with a hosted provider, a
disclosure problem.

## Providers

The pipeline calls `understand_turn(transcript, context)` and does not know
what is behind it.

| Provider | Data leaves the machine | Notes |
| --- | --- | --- |
| `null` | no | Disabled. The default. |
| `mock` | no | Keyword rules, no model. For testing the plumbing. Registered SIMULATED, and `make clu-eval` refuses to report numbers from it. |
| `ollama` | no | A model on this machine. Keeps the synopsis's on-premise claim intact. |
| `openai` | **yes** | Any OpenAI-compatible endpoint: Groq, OpenRouter, Together, Gemini's compatibility layer. |

**On data residency.** The synopsis argues this system can run inside a
bank's perimeter rather than sending customer audio to a third-party cloud.
A hosted provider breaks that, for the turns that reach it. So
`leaves_machine` is part of the provider contract, the capability registry
says it on the dashboard, and every affected turn carries
`data_left_the_machine: true` in its trace. It is a real trade-off and it is
recorded rather than argued away. For a deployment, use `ollama`.

## Enabling it

```
cp .env.example .env          # then edit .env, which is gitignored
```

```
BFSI_CLU_PROVIDER=openai
BFSI_LLM_API_KEY=<key from https://console.groq.com/keys>
BFSI_CLU_MODEL=llama-3.3-70b-versatile
```

Then:

```
make clu-check     # is it configured and does it answer
make clu-models    # what the provider actually offers today
make clu-eval      # baseline against baseline+CLU, writes docs/CLU_RESULTS.md
```

Locally instead:

```
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b-instruct
```
```
BFSI_CLU_PROVIDER=ollama
BFSI_CLU_MODEL=qwen2.5:3b-instruct
```

## Audit

Every turn that reaches the model gets a `clu` stage in its ComplianceTrace
carrying provider, model, prompt version, latency, token counts, the
validated result, which reading the turn actually used, whether an override
was refused and why, and whether data left the machine. A turn where the
router declined to call records that too, with the reason.

`clu_source` on the trace is `baseline` or `clu`, so an auditor can separate
model-influenced decisions from purely deterministic ones with one query.

## Failure behaviour

Every failure path lands in the same place: the deterministic reading.

- provider down, timing out, unauthenticated, or rate limited
- output that is not JSON, or is fenced, truncated or prefixed with prose
- an intent outside the fixed set, a language outside the three, a
  confidence outside [0, 1]
- the provider raising anything at all

`understand_turn` never raises. The worst case is the system we already had,
which is the reason this was safe to try.

## Evaluation

`data/eval/clu_cases.json`, 40 hand-labelled cases across English, Hindi and
Marathi in both scripts, Hinglish, Maringlish, compound requests, follow-ups,
corrections, disfluency, ambiguity, out-of-scope probes and one prompt
injection. `make clu-eval` runs both systems over the same cases in one pass
and writes `docs/CLU_RESULTS.md`.

Measured: intent accuracy overall and per group, compound handling, context
resolution, entity extraction, code-mix detection, must-refuse and
must-escalate retention, latency, call rate and token counts.

The baseline is never removed. If the CLU does not win, the honest outcome is
to leave it off and report that.
