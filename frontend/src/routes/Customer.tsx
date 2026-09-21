import { useEffect, useRef, useState } from 'react'
import { api, type Customer, type Trace } from '../api'

// The customer console. Every voice interaction is also drivable by typing,
// and the pipeline after the transcript is identical, so the demo survives a
// dead microphone in the review room.

type Msg = { who: 'bot' | 'user'; text: string; trace?: Trace }

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

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  useEffect(() => {
    api.customers()
      .then((d) => {
        setCustomers(d.customers)
        setCustomerId(d.presenter_id || d.customers[0]?.customer_id || '')
      })
      .catch((e) => setError('Could not load customers: ' + String(e).slice(0, 140)))
  }, [])

  const selected = customers.find((c) => c.customer_id === customerId)

  const describe = (c: Customer) => {
    const bits = [`${c.accounts} account${c.accounts === 1 ? '' : 's'}`]
    if (c.holdings) bits.push(`${c.holdings} holdings`)
    bits.push(c.enrolled ? `voice enrolled (${c.source})` : 'no voice yet')
    return `${c.customer_id}${c.is_presenter ? ' (demo persona)' : ''}: ${bits.join(', ')}`
  }

  const start = async () => {
    setError(null)
    try {
      const out = await api.startSession({
        customer_id: customerId,
        device_id: 'demo-laptop-' + Math.random().toString(36).slice(2, 7),
        // Text-mode speaker verification needs a sample. In voice mode the
        // query audio is the sample; here we attach a seeded clip so the
        // tier 1 beat is performable without a microphone.
        // Only the three seeded customers have a clip on disk. Sending a
        // filename that does not exist used to blow up the first account turn.
        voice_clip: attachVoice && selected?.enrolled ? `${customerId}_0.wav` : null,
        accepted: true,
      })
      setSessionId(out.session_id); setConsent(out)
      setMsgs([{ who: 'bot', text: out.consent_notice.en }])
    } catch (e: any) { setError(String(e)) }
  }

  const speak = async (text: string, lang: string) => {
    const blob = await api.speak(text, lang)
    if (blob && blob.size > 0) new Audio(URL.createObjectURL(blob)).play().catch(() => {})
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
    } catch (e: any) { setError(String(e)) }
    finally { setBusy(false) }
  }

  const toggleRecord = async () => {
    if (recording) { recorder.current?.stop(); setRecording(false); return }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
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
      const out = await api.enroll(customerId, enrolClips.current)
      setEnrolResult(`Enrolled ${customerId} from ${out.n_clips} live clips, mean pairwise ` +
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
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
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
                </select>
              </div>
              <label className="muted" style={{ display: 'block', marginBottom: 8 }}>
                <input type="checkbox" style={{ width: 'auto', marginRight: 6 }}
                       checked={attachVoice} onChange={(e) => setAttachVoice(e.target.checked)} />
                Attach a seeded clip for the dead-microphone fallback
                {selected && !selected.enrolled && ' (no voice on file for this customer, enrol your own)'}
              </label>
              <button onClick={start} disabled={!customerId}>Give consent and start</button>
            </>
          ) : (
            <>
              <p className="mono" style={{ fontSize: 13 }}>session {sessionId.slice(0, 8)} | consent {consent?.consent_ref?.slice(0, 8)}</p>
              <p className="muted">
                Purpose: {consent?.purpose} Retention: {consent?.retention_days} days.
                Consent is ledger record #{consent?.ledger_index}.
              </p>
              <div className="row">
                <button className="danger" onClick={async () => {
                  await api.withdraw(sessionId); setMsgs((m) => [...m, { who: 'bot', text: 'Consent withdrawn. The vault and transcripts for this session have been purged and a purge record was appended to the ledger.' }]); setSessionId(null)
                }}>Withdraw consent and purge</button>
              </div>
            </>
          )}
        </div>

        {sessionId && (
          <div className="panel">
            <h2>Conversation</h2>
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
              <input value={input} placeholder="Type here, or use the microphone"
                     onChange={(e) => setInput(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter' && !busy) send() }} />
              <button onClick={() => send()} disabled={busy || !input}>Send</button>
              <button className="secondary" onClick={toggleRecord} disabled={busy}>
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
