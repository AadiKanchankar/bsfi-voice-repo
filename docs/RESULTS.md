# Results

Every number on this page was computed by `make eval`, which runs
`backend/app/eval/harness.py` over `data/eval/`. Nothing here is typed in by
hand. If a metric could not be computed, its row says so instead of carrying
a placeholder.

Generated: 2026-09-21T14:07:30.838510+00:00

Evaluation set: 54 hand-labelled utterances across en, hi, mix, mr. The set size is stated next to every
number because a metric without its denominator is not a result.

## Honest limitations, read these first

- The ASR model is `faster-whisper base`, **not fine-tuned on banking audio**.
  The entity-level error rate below is therefore the baseline that a fine-tuned
  model has to beat, and is reported as such.
- Evaluation audio is rendered with Piper, not recorded from humans over a
  telephone line. WER on real telephony audio will be higher.
- **The Hindi, Marathi and code-mixed rows below are not a valid measurement
  of Indic speech recognition.** Those reference transcripts are written in
  romanised Latin script, and rendering them through a Devanagari voice
  produces mispronounced audio that no ASR system could be expected to
  transcribe back to the romanised original. The English rows are the
  interpretable ones. Fixing this needs recorded human audio, which is the
  single highest value next step for the evaluation.
- The anti-spoof component is a classical LFCC and GMM baseline, not AASIST.
- Enrolment voices are synthetic unless a person enrolled through `/enroll`.
- Figures quoted from the literature in the paper (15 to 20 percent WER on
  Earnings-21, up to 72 percent phoneme error reduction from cross-lingual
  pre-training) are literature values for other systems. They are not
  measurements of this system and do not appear in the tables below.

## Language identification (A1)

| Metric | Value | Note |
|---|---|---|
| Dominant language accuracy | 0.7391 | 46 monolingual utterances |
| Mean CMI, code-mixed | 19.9 | 8 utterances, 0 would mean monolingual |
| Mean CMI, monolingual | 9.42 | should be at or near 0 |
| Code-mixed utterances with CMI > 0 | 0.875 | fraction detected as mixed |

> The word-level evidence is a script and lexicon prior, not a trained language identification head. Romanised Hindi and Marathi words outside the seeded function-word lexicon fall through to English, which is what the dominant-language accuracy above is measuring and why the monolingual CMI is not zero. The Viterbi smoother takes posteriors from any source, so a trained head would replace the prior without touching the smoothing.

## Intent classification (A3)

| Metric | Value | Note |
|---|---|---|
| Accuracy on the eval set | 0.8704 | 54 utterances, held out from the head's training bank |
| 5-fold CV accuracy on the seed bank | 0.8304347826086957 | 460 seeded utterances, std 0.06721576014669699 |

Top confusions: `product_info -> fraud_report` x2, `out_of_scope -> branch_ifsc` x2, `product_info -> dispute_txn` x1, `product_info -> limit_change` x1, `out_of_scope -> get_balance` x1

## Retrieval grounding (A4)

| Metric | Value | Note |
|---|---|---|
| Recall@4 | 0.9444 | 18 answerable queries |
| **Similarity floor delta, in use** | 0.5 | lowest floor whose precision still clears 90%, over 18 answerable and 8 unanswerable queries |
| Precision / recall / F1 at that delta | 0.9412 / 0.8889 / 0.9143 | on the same split |
| F1-optimal delta, not used | 0.46 | F1 0.9189, recall 0.9444. Rejected: on a set this size it over-fits, and a real spoken query scored 0.58 against it and was refused. |
| Lowest answerable score / highest unanswerable | 0.1259 / 0.5899 | the gap the floor has to sit inside |
| Mean top score, answerable | 0.6434 |  |
| Mean top score, must-refuse | 0.3633 | the gap between these two rows is what the refusal path lives on |
| Mean top score, answered from core banking | 0.4288 | 28 account and transaction queries, excluded from the calibration: they are neither grounding positives nor must-refuse negatives |
|   answerable top score, en | 0.7179 | 12 queries, lowest 0.6126, 12 of 12 clear the calibrated delta |
|   answerable top score, hi | 0.563 | 2 queries, lowest 0.506, 2 of 2 clear the calibrated delta |
|   answerable top score, mix | 0.6146 | 2 queries, lowest 0.5936, 2 of 2 clear the calibrated delta |
|   answerable top score, mr | 0.3054 | 2 queries, lowest 0.1259, 0 of 2 clear the calibrated delta |

> The policy knowledge base is written in English. A Hindi or Marathi phrasing of the same question therefore scores lower through the cross-lingual gap in the embedding, not because the question is less answerable, and a single global floor refuses some of them. The rows above make that visible. Two reasonable fixes exist and neither is implemented here: a per-language floor, or a knowledge base with translated passages. This is a finding worth reporting in the paper rather than a bug to hide.

## Speech recognition (A9)

| Metric | Value | Note |
|---|---|---|
| WER | 0.6567 | 54 utterances, 402 reference words, model faster-whisper/base/int8 |
| Substitutions / deletions / insertions | 156 / 22 / 86 |  |
|   WER, en | 0.0944 | 28 utterances, 233 reference words |
|   WER, hi | 1.0333 | 10 utterances, 60 reference words |
|   WER, mix | 1.9429 | 8 utterances, 70 reference words |
|   WER, mr | 1.1282 | 8 utterances, 39 reference words |
| **Entity-level error rate** | 0.5294 | 34 financial entities. This is the headline accuracy claim and the baseline a fine-tuned model must beat. |
|   error rate, amount | 0.5714 | 7 entities |
|   error rate, card_last4 | 0.5 | 2 entities |
|   error rate, cheque_number | 0.0 | 1 entities |
|   error rate, payee | 0.6 | 5 entities |
|   error rate, product_name | 0.5263 | 19 entities |
|   error rate, en audio | 0.1579 | 19 entities |
|   error rate, hi audio | 1.0 | 5 entities |
|   error rate, mix audio | 1.0 | 7 entities |
|   error rate, mr audio | 1.0 | 3 entities |
| ASR latency p50 / p95 | 1344.9 ms / 4096.6 ms | CPU, int8 |

### Speech recognition providers, compared

R5 asks for word error and entity error per provider. Only one provider has
been run, and the table says so rather than leaving an implied comparison.

| Provider | WER | Status |
|---|---|---|
| faster-whisper base int8 (local) | see above | measured |
| Sarvam Saarika | not measured | no API key in this repository; the provider reports itself unavailable and every call falls back to the local stack |

A key would let this row be filled in. Until then there is no comparison to
report, and inventing one from the vendor's published figures would be the
kind of number this project does not print.

**The Hindi, Marathi and code-mixed rows above are not a valid measurement,
and no provider comparison built on this audio would be either.** The clips
are rendered with Piper, so a word error rate over 1.0 is largely a
synthesiser transcribing its own output through two models. The apparatus
for replacing them with human recordings is in place:
`data/eval/scripts/{en,hi,mr,mix}.md` and the `/record` page, which captures
through the same microphone constraints the call path uses. See DECISIONS
D34.

## Speaker verification and anti-spoofing (A6)

| Metric | Value | Note |
|---|---|---|
| Speaker EER | 0.125 | 8 target and 24 non-target trials over 4 speakers, model speechbrain/spkrec-ecapa-voxceleb@cosine. Trials: held-out clips, phrases the enrolment never saw. |
| theta at EER | 0.7968 | written to runtime/calibration.json and used by the live system |
| Countermeasure EER | 0.0 | 8 bona fide and 12 spoof clips, LFCC+GMM baseline (BASELINE, not AASIST) |
| min t-DCF (normalised) | undefined at this operating point | the speaker verification system already rejects every spoof at its own threshold, so the countermeasure carries no tandem cost. C1 = 0.6935, C2 = 0.0, priors {'pi_target': 0.9405, 'pi_nontarget': 0.009499999999999995, 'pi_spoof': 0.05}, costs {'C_miss': 1.0, 'C_fa': 10.0} |

> Both classes originate from a text to speech system, because no human speech is collected in this build, so what is measured is the separation of two synthesis conditions and not human speech from deepfakes. Both classes now pass through the same simulated telephony channel. That matters: when only the bona fide clips were band-limited, the mixture model learned "wideband means spoof" and scored a clean recording of the enrolled speaker at 0.02. It was a bandwidth detector with a countermeasure's name on it. Sharing the channel forces it onto voice and vocoder cues.

> enrolment audio is synthetic unless a live voice was enrolled

> **Channel mismatch is the practical limit on the verification path.** The same synthetic speaker scores 0.94 against their enrolment when the trial comes through the same simulated telephony channel, and 0.50 when it arrives as clean wideband audio, against a threshold of about 0.76. Enrolment and verification have to come through the same channel. For the live demo that means enrolling a real voice from the same microphone, which the customer console now supports; the seeded synthetic enrolments are for the text path.

## Latency per stage

From 338 recorded traces. The p95 for the `nlu` stage includes the first turn after a cold start, which pays the one-off embedding model load; the server warms that at startup so a live demo does not see it.

| Stage | n | p50 ms | p95 ms |
|---|---|---|---|
| **turn total** | 338 | 314.39 | 5044.13 |
| anomaly | 268 | 0.16 | 0.42 |
| antispoof | 83 | 0.18 | 0.3 |
| asr | 144 | 1249.51 | 5056.14 |
| clu | 268 | 227.41 | 466.19 |
| fusion | 268 | 0.13 | 0.2 |
| langid | 338 | 0.23 | 0.59 |
| nlu | 268 | 39.85 | 183.32 |
| otp | 41 | 0.03 | 0.06 |
| pii_redaction | 338 | 0.8 | 1.66 |
| policy | 268 | 0.05 | 0.1 |
| readback | 29 | 0.03 | 0.05 |
| retrieval | 96 | 37.49 | 61.06 |
| risk | 268 | 0.07 | 0.16 |
| speaker_verify | 180 | 0.46 | 547.26 |
| text_input | 194 | 0.04 | 0.11 |
| vad | 144 | 26.83 | 53.59 |

## End to end latency on the audio path

Measured 2026-09-21 over 120 audio turns, 30 per language path, on the development laptop with the local stack (faster-whisper base int8 and Kokoro). Models were warmed first; the warm up itself took 6.8 s and is a startup cost, not a per-turn one.

**The metric that matters** is the end of the caller's speech to the first audible reply. It is reported twice: time to any audio, and time to the audio of the actual answer. They are identical today, because nothing is streamed and no acknowledgement is spoken. Both columns are kept so that a filler added later cannot be counted as a real improvement.

- Not included: the contextual language layer, which is an optional cloud call and was disabled for this measurement; on a free tier its rate-limit backoff reached 96 s on a single turn, which would have reported the vendor's queue as this system's latency
- Not included: network transfer and browser playback start, which are client side; these numbers are a lower bound on what a caller experiences
- Not included: endpoint detection, because the evaluation clips are pre-trimmed files and there is no endpointing decision to time

| Path | turns | clips | before p50 | before p95 | after p50 | after p95 |
|---|---|---|---|---|---|---|
| en | 30 | 28 | 5277.9 | 15242.2 | 2731.7 | 5094.7 |
| hi | 30 | 10 | 5559.9 | 8494.3 | 2730.8 | 4782.9 |
| mix | 30 | 8 | 5612.5 | 8947.5 | 3651.0 | 4879.0 |
| mr | 30 | 8 | 6479.5 | 11413.9 | 3054.2 | 8280.1 |
| **all** | 120 | | **5577.0** | **9394.5** | **2976.2** | **5094.7** |

All figures in milliseconds. **Before** is waiting for the whole reply to be synthesised, which is what the system did. **After** is waiting only for its first phrase, which is what it does now: the remaining phrases are made while the first one plays.

That is 47% off the p50 wait, from 5.6 s to 3.0 s. The change request's target is 1.2 s, so this does not reach it. What blocks the rest is named below.

### Where the time goes

| Stage | n | p50 ms | p95 ms |
|---|---|---|---|
| voice activity detection | 120 | 26.5 | 44.7 |
| speech recognition | 120 | 956.3 | 2361.8 |
| intent and slots | 120 | 23.7 | 31.3 |
| policy retrieval | 120 | 0.0 | 25.5 |
| risk and gate | 120 | 0.1 | 0.1 |
| everything to the reply text | 120 | 1483.0 | 4110.1 |
| speech synthesis, whole reply | 120 | 3792.4 | 6548.8 |
| speech synthesis, first phrase only | 120 | 1298.4 | 2062.6 |

**What blocks the 1.2 s target.** With the whole reply no longer on the caller's clock, the two remaining costs are speech recognition and the first phrase of synthesis. Recognition finishes only after the caller stops speaking, so the way to remove it is to transcribe while they are still talking; that is a streaming recogniser and a larger piece of work than anything above. The deterministic pipeline this project is actually about, intent through risk and the gate, costs under a tenth of a second in total and is not worth optimising.

Clips were cycled to reach the target turn count where a language has fewer than 30 of them (repeat factor {'en': 1.1, 'hi': 3.0, 'mr': 3.8, 'mix': 3.8}). Repeating a clip adds nothing to an accuracy measurement, but for latency it is sound: the same audio is the same work, and what is being measured is how long that work takes.

## Escalation rate, before and after the clarify path

Measured over the 54 evaluation utterances with verification refreshed each
turn, so that verification expiry could not be counted as a confidence
problem.

| Outcome | Count | What it is |
|---|---:|---|
| automated | 19 | answered |
| refused | 6 | correctly declined |
| escalated, tier 3 override | 11 | fraud, disputes, investment advice: mandatory |
| escalated, awaiting one time password | 14 | not an escalation, see below |
| escalated, low confidence | 3 | the case `clarify` exists for |
| clarify | 1 | asked instead of transferring |

**Was the system over-escalating? Not on confidence.** Four turns out of 54,
under 8%, turn on the confidence check, and those are the only ones the
clarify path can affect. The rest are tier 3 hard overrides, which are
mandatory and would be unaffected by anything R6 does.

**The reported rate was inflated by about 40%.** Fourteen of the
thirty-four escalations are tier 2 turns asking for a one time password. No
human is involved and no handover packet is created; the caller supplies the
code and the transaction proceeds. A real escalation is one with a
`handover_packet_ref`, and these have none. The label has not been changed,
because an existing test asserts it; see DECISIONS D35 for the
recommendation.

**Why `clarify` fires only once here.** This evaluation set is mostly clean,
single-intent utterances. The case it exists for is the compound,
code-mixed request that a single-label intent head cannot represent and is
therefore not confident about, which is a real caller behaviour that a
synthetic set under-represents. That is an argument for the human
recordings in D34, not against the feature.

## Voice quality: blind listening check

**Not yet run.** The material is generated and waiting for listeners:
`python scripts/listening_check.py` writes six A/B pairs into
`listening-check/` with a scoring sheet, and randomises which side is
which so the file names carry no information.

Each pair differs only in the spoken-text normaliser, which is the change R5
made to pronunciation: amounts in the Indian system, codes spelled out,
digits grouped. The voice model is identical on both sides, so the
comparison isolates the change rather than measuring two differences at
once.

When the team has scored it, the count of pairs where the normalised side
won, and the number of listeners, go here. If it does not win, that goes
here instead.

## Reproducing this page

```
make seed
make eval-audio
make eval
```
