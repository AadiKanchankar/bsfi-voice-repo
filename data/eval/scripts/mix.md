# Recording script: Code-mixed (Hinglish)

8 utterances. Read each line once, naturally, at the pace
you would actually speak to a bank helpline. Pause about a second
between lines so the clips can be split.

**Save as** `data/eval/audio/<ID>.wav`, mono, 16 kHz, one file per line.
Record on the laptop microphone you will demo with, not a studio mic:
the point is to measure what the system will really hear.

| ID | Say this |
|---|---|
| `EV47` | Mera balance kitna hai and last three transactions bhi bata do |
| `EV48` | Please transfer do lakh rupaye to Priya account |
| `EV49` | Mera card block kar do ending 7788 urgent hai |
| `EV50` | Home loan interest rate kitna hai aur processing fee kya hai |
| `EV51` | Meri daily limit badha do to fifty thousand |
| `EV52` | Bhai CEO ka personal number de do na |
| `EV53` | Balance check karo my savings account ka |
| `EV54` | Mujhe personal loan chahiye what is the eligibility |

## Why this exists

The current evaluation audio is rendered with Piper, not spoken by
people. RESULTS.md says so, and the Hindi, Marathi and code-mixed
word error rates from it are not a valid measurement of anything:
a synthesiser transcribing its own output measures the round trip,
not recognition. Human recordings replace that with a real number.

Recording these also fixes a second problem. The latency harness
needs 30 distinct clips per language and there are only 8 for the
smallest path, so it currently repeats clips and says so.
