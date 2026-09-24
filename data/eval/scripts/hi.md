# Recording script: Hindi

10 utterances. Read each line once, naturally, at the pace
you would actually speak to a bank helpline. Pause about a second
between lines so the clips can be split.

**Save as** `data/eval/audio/<ID>.wav`, mono, 16 kHz, one file per line.
Record on the laptop microphone you will demo with, not a studio mic:
the point is to measure what the system will really hear.

| ID | Say this |
|---|---|
| `EV29` | Mera account balance kitna hai |
| `EV30` | Mujhe pichhle teen transactions batao |
| `EV31` | Mera debit card block kar do |
| `EV32` | Rohan ko pachas hazaar rupaye bhej do |
| `EV33` | Home loan ka interest rate kya hai |
| `EV34` | Fixed deposit par kitna byaj milta hai |
| `EV35` | Mere account se fraud hua hai |
| `EV36` | Mujhe agent se baat karni hai |
| `EV37` | CEO ka mobile number kya hai |
| `EV38` | Mera cheque clear hua kya |

## Why this exists

The current evaluation audio is rendered with Piper, not spoken by
people. RESULTS.md says so, and the Hindi, Marathi and code-mixed
word error rates from it are not a valid measurement of anything:
a synthesiser transcribing its own output measures the round trip,
not recognition. Human recordings replace that with a real number.

Recording these also fixes a second problem. The latency harness
needs 30 distinct clips per language and there are only 8 for the
smallest path, so it currently repeats clips and says so.
