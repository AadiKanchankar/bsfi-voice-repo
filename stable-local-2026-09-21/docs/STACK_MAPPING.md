# Stack mapping

The synopsis names a production stack. A laptop demo cannot carry that weight,
so each component is substituted deliberately. Every substitution is a scoping
decision, recorded here so that nobody has to guess which parts are real.

The rule applied throughout: a substitute may be smaller than the production
component, but it must not pretend to be it. Where the substitute is weaker in
kind rather than only in size, the capability registry marks it `BASELINE` or
`SIMULATED` and the dashboard prints that label.

## Speech and language

| Synopsis / paper | This demo | Why | Registry |
| --- | --- | --- | --- |
| Whisper large-v3 fine-tuned on banking audio, IndicConformer | `faster-whisper base`, int8, CPU | Real-time on a laptop CPU with no GPU. IndicConformer stays behind `BFSI_INDIC_CONFORMER=1` for a GPU machine. | `REAL`, with a note that it is not fine-tuned |
| A trained language identification head, continuous | Per-word script and lexicon prior, smoothed with Viterbi | The smoother is the contribution and it takes posteriors from any source. A trained head drops into the same signature. | `REAL`, with a note on the posterior source |
| IndicBERT plus Rasa | `paraphrase-multilingual-MiniLM-L12-v2` embeddings with a logistic-regression head | No training infrastructure, two second fit, swappable interface, calibrated posterior for the fusion step | `REAL` |
| IndicTTS, Parler-TTS | Kokoro-82M ONNX, with Piper as automatic fallback | Offline and CPU, real-time factor about 0.35 measured on the development laptop. Piper alone sounded robotic enough that a tester said so unprompted. No Marathi voice exists in either engine, so Marathi is spoken with the Hindi one. | `REAL`, with the Marathi note |
| ECAPA-TDNN | `speechbrain/spkrec-ecapa-voxceleb`, pretrained | This is the same model the synopsis names | `REAL` |
| AASIST countermeasure | LFCC features with a two class GMM log-likelihood ratio | A trained AASIST is out of scope. This is a real classical baseline behind the interface a real countermeasure would implement. | `BASELINE` |
| Silero VAD | Silero VAD v6 ONNX | Same component | `REAL` |

## Data and application layer

| Synopsis | This demo | Why |
| --- | --- | --- |
| PostgreSQL with pgvector | SQLite with numpy cosine | Zero setup, and beat 10 of the demo needs a presenter to edit a stored row with raw SQL in front of an audience |
| SQLModel or an ORM | stdlib `sqlite3` | An ORM between the demo and the bytes would add a layer to explain and nothing to the demo. The prompt's library list names SQLModel; this is a deliberate simplification and the only one taken against that list. |
| Redis for session state | An in-process dict plus the `sessions` table | Single process. The session tier ratchet is persisted in the table so it survives a reconnect; only the pending-OTP state is in memory. |
| MinIO or S3 | A local AES-256-GCM encrypted vault table and directory | Same confidentiality guarantee, no service to run |
| Keycloak with OAuth 2.0 | Signed JWT with four hardcoded roles | Demo-scale RBAC with the same access matrix. The token issuer at `POST /auth/demo-token` exists only because there is no identity provider. |
| Asterisk with SIP and WebRTC | Browser `MediaRecorder` over a WebSocket, plus an HTTP audio endpoint | No telephony stack in a review room |
| Prometheus and Grafana | Structured stage timings read off the traces, rendered in the dashboard | The dashboard already exists and the timings are already in the trace |
| gRPC alongside REST | REST and one WebSocket | One protocol is enough at this scale |
| Docker and Kubernetes | `make demo` | Cold start under 60 seconds beats orchestration here |
| MLflow | `runtime/seed_manifest.json` and `runtime/calibration.json` | Two models, one seed, one calibration file |
| Presidio | Hand-written regex plus Luhn and Verhoeff | Both checksums are short, are genuine algorithms worth having in the report, and avoid a large dependency for a demo. Verhoeff is what stops every 12-digit number being tokenised as an Aadhaar number. |
| Blockchain audit trail (paper Section IV) | SHA-256 hash chain with HMAC-SHA-256 signatures and checkpoints | The synopsis already argues for this: comparable auditability, far lower operational cost. Paper Section IV should be updated to match. |

## Things that are simply not there

| Component | Status | What the demo does instead |
| --- | --- | --- |
| Core banking | `SIMULATED` | `backend/app/banking/mock_core.py`, a documented interface over synthetic rows |
| OTP delivery | `SIMULATED` | Fixed demo code `123456`, no SMS gateway |
| Agent console | `SIMULATED` | The handover queue in the dashboard. The context packet is real and complete; there is no human on the other end. |
| Telephony | not present | Browser microphone, or typing |

## Changed after listening to a recording of it talking

A tester recorded an 88 second session and sent it back. Four things came out
of it, and all four are fixed:

| What the recording showed | Cause | Fix |
| --- | --- | --- |
| The Hindi "feels very different" | Every Hindi and Marathi reply was written in romanised Latin. Both engines phonemise from script, so espeak's Hindi phonemiser read Latin letters with English vowels: "khatam hone wale" became `kˈɑːtam hˈəʊn wˈeɪl`. | Every template rewritten in Devanagari, with `tts.assert_devanagari` refusing to speak a romanised one and a test walking every template. |
| The voice is robotic | Piper medium voices, plus replies that read out "206,465.68" and "POL-HL-001 version 1.1" literally. | Kokoro-82M as the primary engine, amounts and identifiers spoken as words in all three languages, document identifiers no longer read aloud. |
| It stopped understanding context | One garbled transcript was classified `dispute_txn`, which hard-overrides to tier 3 and pinned the session floor there. Every later turn escalated, including public-information questions. | The floor only moves on a confident escalation, public intents are exempt from it, and it decays after clean turns. |
| Verification "clearly didn't verify" | Text turns re-scored a seeded WAV off disk and reported it as the caller's verification. Picking a customer without a seeded clip crashed the turn outright. | A voice check is now a separate live recording with a five minute, five turn expiry. The seeded-clip path still exists for a dead microphone and is labelled SIMULATED wherever it appears. |

A fifth came out of fixing the fourth: the similarity floor had been calibrated
to F1 on a 54 item set and landed on 0.59, and a real spoken question scored
0.58 and was refused. See ALGORITHMS.md A4.

## Deliberate deviations from the build prompt

Two, both listed for review:

1. **stdlib `sqlite3` instead of SQLModel.** Reasons above. Reversible: the
   schema is plain SQL in `backend/app/db.py`.
2. **Risk components stored unrounded.** The prompt does not specify
   precision, but the property test requires that a reviewer recomputing the
   score from the trace lands on the stored value exactly, and rounded
   components cannot do that. Display rounding happens in the dashboard.

## Environment notes that matter on the demo machine

- `PRAGMA synchronous=NORMAL` is set alongside WAL. On the development machine
  the default `FULL` cost roughly 0.4 seconds per commit, which made a
  thousand-record ledger unusable. With WAL a power loss can lose the last few
  commits but cannot corrupt the chain.
- `HF_HUB_DISABLE_XET=1` is exported by the Makefile. The Hugging Face Xet
  transfer backend stalled on the development network and left zero byte
  downloads behind.
- Model downloads use an allow list rather than a full repository snapshot.
  The embedding repository carries the same weights in five formats, several
  gigabytes in total, and one of them is needed.
