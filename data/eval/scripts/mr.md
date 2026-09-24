# Recording script: Marathi

8 utterances. Read each line once, naturally, at the pace
you would actually speak to a bank helpline. Pause about a second
between lines so the clips can be split.

**Save as** `data/eval/audio/<ID>.wav`, mono, 16 kHz, one file per line.
Record on the laptop microphone you will demo with, not a studio mic:
the point is to measure what the system will really hear.

| ID | Say this |
|---|---|
| `EV39` | Majhya khatyat kiti paise aahet |
| `EV40` | Majhe shevatche teen vyavhar sanga |
| `EV41` | Majha card band kara |
| `EV42` | Gruh karjacha vyajdar kiti aahe |
| `EV43` | Kothrud shakhecha IFSC code sanga |
| `EV44` | Majhya khatyat fasavnuk zali aahe |
| `EV45` | Mala manasashi bolaycha aahe |
| `EV46` | Aaj Pune madhe havaman kase aahe |

## Why this exists

The current evaluation audio is rendered with Piper, not spoken by
people. RESULTS.md says so, and the Hindi, Marathi and code-mixed
word error rates from it are not a valid measurement of anything:
a synthesiser transcribing its own output measures the round trip,
not recognition. Human recordings replace that with a real number.

Recording these also fixes a second problem. The latency harness
needs 30 distinct clips per language and there are only 8 for the
smallest path, so it currently repeats clips and says so.
