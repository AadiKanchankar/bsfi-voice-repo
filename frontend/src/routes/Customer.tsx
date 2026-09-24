import { useEffect, useRef, useState } from 'react'
import { api, type Customer, type Trace } from '../api'

// The customer console. Every voice interaction is also drivable by typing,
// and the pipeline after the transcript is identical, so the demo survives a
// dead microphone in the review room.

type Msg = { who: 'bot' | 'user'; text: string; trace?: Trace }

// The three constraints the change request names. Echo cancellation is the
// load-bearing one: without it the assistant's own voice returns through the
// microphone and reads as the caller speaking, so it would barge in on
// itself. A headset is still recommended in the runbook.
const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
}

// The picker is built from GET /customers, never a hardcoded list. A
// hardcoded one is how the demo persona ended up in the seed data but not on
// screen.

export default function Customer() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [consent, setConsent] = useState<any>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [customerId, setCustomerId] = useState('')
  const [customers, setCustomers] = useState<Customer[]>([])
  const [attachVoice, setAttachVoice] = useState(true)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  const [enrolStep, setEnrolStep] = useState(-1)
  const [verifyState, setVerifyState] = useState<any>(null)
  const [enrolResult, setEnrolResult] = useState<string | null>(null)
  const enrolClips = useRef<Blob[]>([])
  const [showRegister, setShowRegister] = useState(false)
  const [regName, setRegName] = useState('')
  const [regMobile, setRegMobile] = useState('')
  const [regLanguage, setRegLanguage] = useState('en')
  const [identifier, setIdentifier] = useState('')
  const [identified, setIdentified] = useState<any>(null)
  const [callId, setCallId] = useState<string | null>(null)
  const [callState, setCallState] = useState<string>('')
  const player = useRef<HTMLAudioElement | null>(null)
  const speaking = useRef<{ text: string; startedAt: number } | null>(null)
  const speakToken = useRef(0)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  useEffect(() => {
    api.customers()
      .then((d) => {
        setCustomers(d.customers)
        setCustomerId(d.presenter_id || d.customers[0]?.customer_id || '')
      })
      .catch((e) => setError('Could not load customers: ' + String(e).slice(0, 140)))
  }, [])

  // Whoever this call is actually about: the picked customer, or the one who
  // identified themselves after an anonymous call opened.
  const activeId = customerId || identified?.customer_id || ''
  const selected = customers.find((c) => c.customer_id === activeId)

  const describe = (c: Customer) => {
    const bits = [`${c.accounts} account${c.accounts === 1 ? '' : 's'}`]
    if (c.holdings) bits.push(`${c.holdings} holdings`)
    bits.push(c.enrolled ? `voice enrolled (${c.source})` : 'no voice yet')
    return `${c.customer_id}${c.is_presenter ? ' (demo persona)' : ''}: ${bits.join(', ')}`
  }

  // Registration and identification are two halves of the same thing. You
  // register once to create the customer and enrol a voice against it; you
  // identify on every later call so the check knows whose voice to compare.
  const reloadCustomers = async (select?: string) => {
    const d = await api.customers()
    setCustomers(d.customers)
    if (select) setCustomerId(select)
  }

  const registerCustomer = async () => {
    setError(null); setBusy(true)
    try {
      const out = await api.register({ name: regName, mobile: regMobile || undefined, language: regLanguage })
      await reloadCustomers(out.customer_id)
      setShowRegister(false); setRegName(''); setRegMobile('')
      setEnrolResult(`Registered ${out.customer_id}. Mobile stored as ${out.mobile_masked || 'not given'}. ` +
        'Start a session and record three clips to enrol a voice against it.')
    } catch (e: any) { setError('Registration failed: ' + String(e).slice(0, 200)) }
    setBusy(false)
  }

  const identifyCaller = async () => {
    if (!sessionId) return
    setError(null); setBusy(true)
    try {
      const out = await api.identify(sessionId, identifier)
      setIdentified(out)
      setMsgs((m) => [...m, {
        who: 'bot',
        text: out.identified
          ? `Thank you. I have found your record, ${out.name}. ${out.enrolled
              ? 'I will now check your voice against the one on file.'
              : 'There is no voice on file for you yet, so I will ask a security question instead.'}`
          : out.reason || 'I could not match that.',
      }])
    } catch (e: any) { setError('Identification failed: ' + String(e).slice(0, 200)) }
    setBusy(false)
  }

  const start = async () => {
    setError(null)
    try {
      const out = await api.startSession({
        customer_id: customerId || null,
        device_id: 'demo-laptop-' + Math.random().toString(36).slice(2, 7),
        // Text-mode speaker verification needs a sample. In voice mode the
        // query audio is the sample; here we attach a seeded clip so the
        // tier 1 beat is performable without a microphone.
        // Only the three seeded customers have a clip on disk. Sending a
        // filename that does not exist used to blow up the first account turn.
        voice_clip: attachVoice && selected?.enrolled ? `${customerId}_0.wav` : null,
        accepted: true,
      })
      setSessionId(out.session_id); setConsent(out); setIdentified(null)
      setCallId(out.call_id)
      // Read the state back rather than assuming it. The server
      // decides, and a browser that prints its own guess is the
      // thing this whole change is meant to stop.
      try { setCallState((await api.callState(out.call_id)).state) }
      catch { setCallState('') }
      setMsgs([{ who: 'bot', text: out.consent_notice.en }])
    } catch (e: any) { setError(String(e)) }
  }

  // One player, so a new reply replaces the previous one instead of playing
  // over it. The double-voice bug was two Audio objects alive at once.
  //
  // The reply is spoken phrase by phrase. Synthesis is 71% of the wait
  // between a caller finishing and hearing an answer (5.0 s of a measured
  // 7.1 s p50), and a reply is about four phrases, so the first one is ready
  // in roughly a quarter of the time and the rest is made while it plays.
  // `turnAt` guards the sequence: if a newer reply starts, or the caller
  // presses Stop, the phrases still in flight are dropped rather than played
  // over the top.
  const speak = async (text: string, lang: string) => {
    player.current?.pause()
    speaking.current = { text, startedAt: performance.now() }
    const mine = ++speakToken.current

    let phrases: string[] = [text]
    try { phrases = (await api.speakPlan(text, lang)).phrases } catch { /* whole reply */ }

    for (const phrase of phrases) {
      if (speakToken.current !== mine) return       // superseded or stopped
      const blob = await api.speak(phrase, lang)
      if (speakToken.current !== mine) return
      if (!blob || blob.size === 0) continue
      const el = new Audio(URL.createObjectURL(blob))
      player.current = el
      await new Promise<void>((done) => {
        el.onended = () => done()
        el.onerror = () => done()
        el.play().catch(() => done())
      })
    }
    if (speakToken.current === mine) { speaking.current = null; refreshCallState() }
  }

  const refreshCallState = async () => {
    if (!callId) return
    try { setCallState((await api.callState(callId)).state) } catch { /* ignore */ }
  }

  // Stop speaking. The server is told how much of the reply was actually
  // heard, because a reply cut off after four words was not delivered and the
  // audit should not record it as though it was.
  const stopSpeaking = async () => {
    if (!callId) return
    const el = player.current
    const spoken = speaking.current
    let playedMs: number | undefined
    let playedChars: number | undefined
    if (el && spoken) {
      playedMs = el.currentTime > 0 ? el.currentTime * 1000
                                    : performance.now() - spoken.startedAt
      const fraction = el.duration > 0 ? Math.min(el.currentTime / el.duration, 1) : 0
      playedChars = Math.round(spoken.text.length * fraction)
    }
    speakToken.current++          // drop any phrases still being fetched
    el?.pause()
    player.current = null
    speaking.current = null
    try {
      const out = await api.interrupt(callId, {
        played_ms: playedMs, played_chars: playedChars,
        reply_chars: spoken?.text.length, source: 'stop_button',
      })
      setCallState(out.state)
      if (out.pending_dropped?.length) {
        setMsgs((m) => [...m, { who: 'bot', text:
          'I have stopped there. Nothing was confirmed and nothing has changed on ' +
          'your account. Tell me again when you are ready.' }])
      }
    } catch (e: any) { setError(String(e).slice(0, 200)) }
  }

  const endCall = async () => {
    if (!callId) return
    speakToken.current++
    player.current?.pause(); player.current = null; speaking.current = null
    try { await api.endCall(callId) } catch { /* the call may already be over */ }
    setCallState('ENDED')
    setMsgs((m) => [...m, { who: 'bot', text: 'Call ended. Thank you for calling.' }])
    setSessionId(null); setCallId(null)
  }

  const send = async (text?: string, extra: any = {}) => {
    if (!sessionId) return
    const body = text ?? input
    setBusy(true); setError(null)
    if (body) setMsgs((m) => [...m, { who: 'user', text: body }])
    setInput('')
    try {
      const trace = await api.textTurn({ session_id: sessionId, text: body || '', ...extra })
      setMsgs((m) => [...m, { who: 'bot', text: trace.reply_text || '(no reply)', trace }])
      if (trace.reply_text) speak(trace.reply_text, trace.reply_language || 'en')
      refreshCallState()
    } catch (e: any) { setError(String(e)) }
    finally { setBusy(false) }
  }

  const toggleRecord = async () => {
    if (recording) { recorder.current?.stop(); setRecording(false); return }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS)
      const mr = new MediaRecorder(stream)
      chunks.current = []
      mr.ondataavailable = (e) => chunks.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setBusy(true)
        try {
          const trace = await api.audioTurn(sessionId!, new Blob(chunks.current))
          setMsgs((m) => [...m, { who: 'user', text: trace.transcript || '(no transcript)' },
                                { who: 'bot', text: trace.reply_text || '(no reply)', trace }])
          if (trace.reply_text) speak(trace.reply_text, trace.reply_language || 'en')
        } catch (e: any) { setError('Microphone path failed, use the text box: ' + String(e).slice(0, 200)) }
        finally { setBusy(false) }
      }
      mr.start(); recorder.current = mr; setRecording(true)
    } catch (e: any) {
      setError('No microphone available. The text box below drives the identical pipeline.')
    }
  }

  // Enrolling a real voice matters more than it looks. The seeded enrolment
  // audio is synthetic and band-limited, so a live microphone recording of the
  // same words scores about 0.50 against a threshold of 0.75: enrolment and
  // verification have to come through the same channel. Enrol here before
  // demonstrating the voice path with a microphone.
  const ENROL_PHRASES = [
    'My voice is my password, and this is a demonstration account.',
    'Please confirm my account balance for the demonstration.',
    'This recording is synthetic and was generated for testing.',
  ]

  const recordEnrolClip = () => recordClip(4, async (blob) => {
    enrolClips.current.push(blob)
    const next = enrolClips.current.length
    setEnrolStep(next)
    if (next < ENROL_PHRASES.length) return
    try {
      const out = await api.enroll(activeId, enrolClips.current)
      setEnrolResult(`Enrolled ${activeId} from ${out.n_clips} live clips, mean pairwise ` +
        `cosine ${out.mean_pairwise_cosine}. Now press Verify my voice: enrolment and ` +
        `verification have to come through the same microphone.`)
    } catch (e: any) { setError('Enrolment failed: ' + String(e).slice(0, 200)) }
    enrolClips.current = []
    setEnrolStep(-1)
  })

  // Record a short clip and hand it to a callback. One helper, two callers:
  // enrolment and verification.
  const recordClip = (seconds: number, done: (b: Blob) => void) => {
    setError(null)
    navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS).then((stream) => {
      const mr = new MediaRecorder(stream)
      const local: Blob[] = []
      mr.ondataavailable = (e) => local.push(e.data)
      mr.onstop = () => { stream.getTracks().forEach((t) => t.stop()); done(new Blob(local)) }
      mr.start()
      setTimeout(() => mr.stop(), seconds * 1000)
    }).catch(() => setError('No microphone available. Use the seeded-clip check below, which is labelled SIMULATED.'))
  }

  const doVerify = () => {
    setVerifyState({ recording: true })
    recordClip(4, async (blob) => {
      try { setVerifyState(await api.verifyVoice(sessionId!, blob)) }
      catch (e: any) { setError(String(e).slice(0, 200)); setVerifyState(null) }
    })
  }

  const doVerifyDemo = async () => {
    try { setVerifyState(await api.verifyDemo(sessionId!)) }
    catch (e: any) { setError(String(e).slice(0, 200)) }
  }

  const script = [
    ['2. Tier 0', 'What are your home loan interest rates'],
    ['3. Refusal', "What is the CEO's personal phone number"],
    ['4. Code-mixed', 'Mera balance kitna hai, and last three transactions bhi bata do'],
    ['4b. Code-mixed, single intent', 'Mera balance kitna hai'],
    ['5. Tier 1', 'What is my account balance'],
    ['6. Tier 2', 'Block my card'],
    ['7. Tier 3', 'Someone has made a fraudulent transaction on my account'],
    ['8. Investments, facts', 'What is my portfolio worth'],
    ['9. Investments, advice', 'Which stock should I buy right now'],
  ]

  return (
    <div className="wrap cols">
      <div>
        <div className="panel">
          <h2>Session</h2>
          {!sessionId ? (
            <>
              <p className="muted">
                Opening a session records consent as the first entry in the audit ledger. The
                notice states the purpose and the retention period before anything is processed.
              </p>
              <div className="row" style={{ marginBottom: 8 }}>
                <select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                  {customers.length === 0 && <option value="">loading customers...</option>}
                  {customers.map((c) => (
                    <option key={c.customer_id} value={c.customer_id}>{describe(c)}</option>
                  ))}
                  <option value="">caller not yet identified (identify during the call)</option>
                </select>
                <button className="secondary" onClick={() => setShowRegister((v) => !v)}>
                  {showRegister ? 'Cancel' : 'Register a customer'}
                </button>
              </div>
              {showRegister && (
                <div className="panel" style={{ marginBottom: 8 }}>
                  <h3>Register a customer</h3>
                  <p className="muted">
                    Only the last four digits of the mobile number are stored. That is
                    enough to identify a caller who states it on a later call.
                  </p>
                  <div className="row" style={{ marginBottom: 6 }}>
                    <input placeholder="Name" value={regName} onChange={(e) => setRegName(e.target.value)} />
                    <input placeholder="Mobile (optional)" value={regMobile}
                           onChange={(e) => setRegMobile(e.target.value)} />
                    <select value={regLanguage} onChange={(e) => setRegLanguage(e.target.value)}>
                      <option value="en">English</option>
                      <option value="hi">Hindi</option>
                      <option value="mr">Marathi</option>
                    </select>
                  </div>
                  <button onClick={registerCustomer} disabled={!regName.trim() || busy}>Create</button>
                </div>
              )}
              <label className="muted" style={{ display: 'block', marginBottom: 8 }}>
                <input type="checkbox" style={{ width: 'auto', marginRight: 6 }}
                       checked={attachVoice} onChange={(e) => setAttachVoice(e.target.checked)} />
                Attach a seeded clip for the dead-microphone fallback
                {selected && !selected.enrolled && ' (no voice on file for this customer, enrol your own)'}
              </label>
              <button onClick={start}>Give consent and start</button>
            </>
          ) : (
            <>
              <p className="mono" style={{ fontSize: 13 }}>session {sessionId.slice(0, 8)} | consent {consent?.consent_ref?.slice(0, 8)}</p>
              <p className="muted">
                Purpose: {consent?.purpose} Retention: {consent?.retention_days} days.
                Consent is ledger record #{consent?.ledger_index}.
              </p>
              {!customerId && !identified?.identified && (
                <>
                  <p className="muted">
                    This call is not yet attached to a customer. The caller states their
                    registered mobile number or customer id; voice verification then runs
                    against that customer's enrolment. Identifying is not authenticating.
                  </p>
                  <div className="row">
                    <input placeholder="Mobile number or customer id" value={identifier}
                           onChange={(e) => setIdentifier(e.target.value)}
                           onKeyDown={(e) => e.key === 'Enter' && identifyCaller()} />
                    <button onClick={identifyCaller} disabled={!identifier.trim() || busy}>Identify</button>
                  </div>
                </>
              )}
              {identified?.identified && (
                <p className="mono" style={{ fontSize: 13 }}>
                  identified as {identified.customer_id} ({identified.name}),
                  {identified.enrolled ? ' voice on file' : ' no voice on file'}
                </p>
              )}
              <div className="row">
                <button className="secondary" data-testid="stop-speaking"
                        onClick={stopSpeaking}>Stop speaking</button>
                <button className="secondary" data-testid="end-call"
                        onClick={endCall}>End call</button>
                <button className="danger" onClick={async () => {
                  await api.withdraw(sessionId); setMsgs((m) => [...m, { who: 'bot', text: 'Consent withdrawn. The vault and transcripts for this session have been purged and a purge record was appended to the ledger.' }]); setSessionId(null); setCallId(null)
                }}>Withdraw consent and purge</button>
              </div>
              <p className="muted" data-testid="call-state">
                call {callId} is {callState || 'starting'}.
                The server decides this, not the browser: that is what stops two
                replies playing over each other.
              </p>
            </>
          )}
        </div>

        {(sessionId || msgs.length > 0) && (
          <div className="panel">
            <h2>Conversation{!sessionId && msgs.length > 0 ? ' (call ended)' : ''}</h2>
            <div style={{ maxHeight: 420, overflowY: 'auto', marginBottom: 10 }}>
              {msgs.map((m, i) => (
                <div key={i} className={'bubble ' + m.who}>
                  {m.text}
                  {m.trace && (
                    <div className="meta">
                      <span className={'pill ' + (m.trace.decision || '')}>{m.trace.decision}</span>{' '}
                      <span className={'pill tier' + (m.trace.risk_tier ?? 0)}>tier {m.trace.risk_tier}</span>{' '}
                      intent {m.trace.intent} | R {m.trace.risk_score?.toFixed(3)} | CMI {m.trace.code_mix_index}
                      {' | '}<a href={`/compliance?trace=${m.trace.trace_id}`}>open in dashboard</a>
                    </div>
                  )}
                </div>
              ))}
              <div ref={endRef} />
            </div>
            <div className="row" style={{ marginBottom: 8 }}>
              <input value={input} placeholder={sessionId ? 'Type here, or use the microphone'
                                                          : 'The call has ended'}
                     disabled={!sessionId}
                     onChange={(e) => setInput(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter' && !busy) send() }} />
              <button onClick={() => send()} disabled={busy || !input || !sessionId}>Send</button>
              <button className="secondary" onClick={toggleRecord} disabled={busy || !sessionId}>
                {recording ? 'Stop' : 'Speak'}
              </button>
            </div>
            <div className="row">
              <button className="secondary" onClick={() => send('', { otp: '123456' })} disabled={busy}>
                Submit OTP 123456
              </button>
              <button className="secondary" onClick={() => send('', { confirm: true })} disabled={busy}>
                Confirm read-back
              </button>
              <button className="secondary" onClick={() => send('', { confirm: false })} disabled={busy}>
                Decline read-back
              </button>
            </div>
            <p className="muted">
              The OTP is a fixed demo code and is registered SIMULATED in the capability
              registry. There is no SMS gateway in this build.
            </p>

            <h3>Voice check</h3>
            <p className="muted">
              Account questions need to know who is speaking. A check is good for five
              minutes or five turns, then it expires and you will be asked again. Typed
              turns carry the last check; they never re-score a stored file and call that
              a verification.
            </p>
            <div className="row">
              <button onClick={doVerify} disabled={busy || !sessionId}>
                {verifyState?.recording ? 'Listening...' : 'Verify my voice'}
              </button>
              <button className="secondary" onClick={doVerifyDemo} disabled={busy || !sessionId}>
                Use seeded clip (SIMULATED)
              </button>
            </div>
            {verifyState && !verifyState.recording && (
              <p style={{ color: verifyState.passed ? 'var(--green)' : 'var(--red)' }}>
                {verifyState.passed
                  ? `Verified. Cosine ${verifyState.cosine} against threshold ${verifyState.threshold}, anti-spoof ${verifyState.spoof_score}, s_verify ${verifyState.s_verify}.`
                  : `Not verified. ${verifyState.reason || ''} ${verifyState.cosine != null ? `Cosine ${verifyState.cosine} against threshold ${verifyState.threshold}.` : ''}`}
                {verifyState.simulated && ' This check ran against a seeded clip, not a live speaker.'}
              </p>
            )}

            <h3>Enrol a real voice</h3>
            <p className="muted">
              The seeded enrolment audio is synthetic and band limited. A live microphone
              recording of the same speaker scores around 0.50 against a threshold of 0.75,
              because enrolment and verification have to come through the same channel.
              Enrol here before demonstrating the voice path with a microphone.
            </p>
            <div className="row">
              <button className="secondary" onClick={recordEnrolClip} disabled={busy}>
                {enrolStep < 0 ? 'Record clip 1 of 3' : `Record clip ${enrolStep + 1} of 3`}
              </button>
              <span className="muted">
                Say: "{ENROL_PHRASES[Math.max(0, enrolStep)]}" (4 seconds)
              </span>
            </div>
            {enrolResult && <p style={{ color: 'var(--green)' }}>{enrolResult}</p>}
          </div>
        )}
        {error && <div className="panel" style={{ borderColor: 'var(--red)' }}><p style={{ color: 'var(--red)' }}>{error}</p></div>}
      </div>

      <div>
        <div className="panel">
          <h2>Demo script</h2>
          <p className="muted">Each button sends the utterance from that beat of the runbook.</p>
          {script.map(([label, text]) => (
            <div key={label} style={{ marginBottom: 6 }}>
              <button className="secondary" style={{ width: '100%', textAlign: 'left' }}
                      disabled={!sessionId || busy} onClick={() => send(text)}>
                <strong>{label}</strong><br /><span className="muted">{text}</span>
              </button>
            </div>
          ))}
        </div>
        {msgs.filter((m) => m.trace).slice(-1).map((m, i) => (
          <div className="panel" key={i}>
            <h2>Last turn at a glance</h2>
            <table>
              <tbody>
                <tr><td>transcript stored</td><td className="mono">{m.trace!.transcript}</td></tr>
                <tr><td>intent</td><td className="mono">{m.trace!.intent} ({((m.trace!.intent_confidence ?? 0) * 100).toFixed(1)}%)</td></tr>
                <tr><td>c_final</td><td className="mono">{m.trace!.fused_confidence} vs tau {m.trace!.tau_required}</td></tr>
                <tr><td>risk</td><td className="mono">R {m.trace!.risk_score?.toFixed(4)} tier {m.trace!.risk_tier}</td></tr>
                <tr><td>decision</td><td>{m.trace!.decision_reason}</td></tr>
              </tbody>
            </table>
            <p className="muted">Full trace, stage by stage, is on the compliance dashboard.</p>
          </div>
        ))}
      </div>
    </div>
  )
}
