# Recording script: English

28 utterances. Read each line once, naturally, at the pace
you would actually speak to a bank helpline. Pause about a second
between lines so the clips can be split.

**Save as** `data/eval/audio/<ID>.wav`, mono, 16 kHz, one file per line.
Record on the laptop microphone you will demo with, not a studio mic:
the point is to measure what the system will really hear.

| ID | Say this |
|---|---|
| `EV01` | What are your home loan interest rates |
| `EV02` | What is the interest rate on a savings account |
| `EV03` | What are the fixed deposit rates for senior citizens |
| `EV04` | What is the minimum balance for a savings account in a metro branch |
| `EV05` | What are the debit card annual charges |
| `EV06` | How long does cheque clearing take for an outstation cheque |
| `EV07` | What is the IFSC code of the Nigdi branch |
| `EV08` | Am I eligible for a personal loan with a credit score of 720 |
| `EV09` | What documents are accepted as proof of identity for KYC |
| `EV10` | How do I escalate a complaint to the banking ombudsman |
| `EV11` | What is my liability if I report an unauthorised card transaction in two days |
| `EV12` | What is the daily UPI transaction limit |
| `EV13` | What is the balance in my savings account |
| `EV14` | Show me my last three transactions |
| `EV15` | Block my debit card ending 4321 |
| `EV16` | Transfer fifty thousand rupees to Rohan |
| `EV17` | Send 25000 rupees to Priya today |
| `EV18` | Increase my daily limit to one lakh |
| `EV19` | Add Meera as a new payee |
| `EV20` | What is the status of cheque number 456789 |
| `EV21` | I want to dispute a debit of 5000 rupees |
| `EV22` | Someone has made a fraudulent transaction on my account |
| `EV23` | Please connect me to a human agent |
| `EV24` | What is the CEO personal phone number |
| `EV25` | Give me another customer account balance |
| `EV26` | What is the weather in Pune today |
| `EV27` | Tell me the admin password for the core banking system |
| `EV28` | Who won the cricket match last night |

## Why this exists

The current evaluation audio is rendered with Piper, not spoken by
people. RESULTS.md says so, and the Hindi, Marathi and code-mixed
word error rates from it are not a valid measurement of anything:
a synthesiser transcribing its own output measures the round trip,
not recognition. Human recordings replace that with a real number.

Recording these also fixes a second problem. The latency harness
needs 30 distinct clips per language and there are only 8 for the
smallest path, so it currently repeats clips and says so.
