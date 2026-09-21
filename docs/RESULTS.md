# Results

Every number on this page was computed by `make eval`, which runs
`backend/app/eval/harness.py` over `data/eval/`. Nothing here is typed in by
hand. If a metric could not be computed, its row says so instead of carrying
a placeholder.

Generated: 2026-09-20T20:39:32.267659+00:00

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
| WER | 0.49 | 54 utterances, 402 reference words, model faster-whisper/base/int8 |
| Substitutions / deletions / insertions | 154 / 23 / 20 |  |
|   WER, en | 0.0944 | 28 utterances, 233 reference words |
|   WER, hi | 1.0167 | 10 utterances, 60 reference words |
|   WER, mix | 1.0 | 8 utterances, 70 reference words |
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
| ASR latency p50 / p95 | 1150.3 ms / 6979.4 ms | CPU, int8 |

## Speaker verification and anti-spoofing (A6)

| Metric | Value | Note |
|---|---|---|
| Speaker EER | 0.125 | 8 target and 24 non-target trials over 4 speakers, model speechbrain/spkrec-ecapa-voxceleb@cosine. Trials: held-out clips, phrases the enrolment never saw. |
| theta at EER | 0.7757 | written to runtime/calibration.json and used by the live system |
| Countermeasure EER | 0.0 | 8 bona fide and 12 spoof clips, LFCC+GMM baseline (BASELINE, not AASIST) |
| min t-DCF (normalised) | undefined at this operating point | the speaker verification system already rejects every spoof at its own threshold, so the countermeasure carries no tandem cost. C1 = 0.6935, C2 = 0.0, priors {'pi_target': 0.9405, 'pi_nontarget': 0.009499999999999995, 'pi_spoof': 0.05}, costs {'C_miss': 1.0, 'C_fa': 10.0} |

> Both classes originate from a text to speech system, because no human speech is collected in this build, so what is measured is the separation of two synthesis conditions and not human speech from deepfakes. Both classes now pass through the same simulated telephony channel. That matters: when only the bona fide clips were band-limited, the mixture model learned "wideband means spoof" and scored a clean recording of the enrolled speaker at 0.02. It was a bandwidth detector with a countermeasure's name on it. Sharing the channel forces it onto voice and vocoder cues.

> enrolment audio is synthetic unless a live voice was enrolled

> **Channel mismatch is the practical limit on the verification path.** The same synthetic speaker scores 0.94 against their enrolment when the trial comes through the same simulated telephony channel, and 0.50 when it arrives as clean wideband audio, against a threshold of about 0.76. Enrolment and verification have to come through the same channel. For the live demo that means enrolling a real voice from the same microphone, which the customer console now supports; the seeded synthetic enrolments are for the text path.

## Latency per stage

From 55 recorded traces. The p95 for the `nlu` stage includes the first turn after a cold start, which pays the one-off embedding model load; the server warms that at startup so a live demo does not see it.

| Stage | n | p50 ms | p95 ms |
|---|---|---|---|
| **turn total** | 55 | 26.21 | 96.59 |
| anomaly | 45 | 0.18 | 0.39 |
| fusion | 45 | 0.17 | 0.33 |
| langid | 55 | 0.18 | 0.47 |
| nlu | 45 | 24.09 | 75.44 |
| otp | 6 | 0.03 | 0.03 |
| pii_redaction | 55 | 0.88 | 2.68 |
| policy | 45 | 0.06 | 0.22 |
| readback | 4 | 0.02 | 0.02 |
| retrieval | 9 | 24.34 | 44.13 |
| risk | 45 | 0.08 | 0.24 |
| speaker_verify | 39 | 0.18 | 0.5 |
| text_input | 55 | 0.05 | 0.15 |

## Reproducing this page

```
make seed
make eval-audio
make eval
```
