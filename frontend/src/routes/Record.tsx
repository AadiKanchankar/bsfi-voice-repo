import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// R5. A page for recording the evaluation set in a human voice.
//
// The evaluation audio today is rendered with Piper, and RESULTS.md says the
// Hindi, Marathi and code-mixed word error rates from it are not a valid
// measurement: a synthesiser transcribing its own output measures the round
// trip, not recognition. This is how that gets replaced with a real number.
//
// Deliberately plain. It is an internal tool for the team, used once, and
// anything more would be effort spent on the wrong thing.

const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'mr', label: 'Marathi' },
  { code: 'mix', label: 'Code-mixed (Hinglish)' },
]

type Line = { id: string; text: string; intent: string | null; recorded: boolean }

export default function Record() {
  const [lang, setLang] = useState('en')
  const [lines, setLines] = useState<Line[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [playing, setPlaying] = useState<Record<string, string>>({})
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  // Recording without listening is not reviewing: you cannot tell whether
  // the microphone was picked up at all until you hear it back.
  const play = async (id: string) => {
    setError(null)
    try {
      const url = await api.evalAudioUrl(id)
      setPlaying((p) => ({ ...p, [id]: url }))
    } catch (e: any) {
      setError(`Could not play ${id}: ${String(e).slice(0, 120)}`)
    }
  }

  const load = async (code: string) => {
    setError(null)
    try { setPlaying({}); setLines((await api.evalScript(code)).lines) }
    catch (e: any) { setError(String(e).slice(0, 200)) }
  }
  useEffect(() => { load(lang) }, [lang])

  const record = async (line: Line) => {
    if (busy) return
    setError(null); setNote(null)
    try {
      // Same constraints as the call path, so what is measured is what the
      // system will actually hear.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      const mr = new MediaRecorder(stream)
      chunks.current = []
      mr.ondataavailable = (e) => chunks.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        try {
          const out = await api.evalRecord(line.id, new Blob(chunks.current))
          setNote(`Saved ${out.id}, ${out.seconds}s.`)
          setLines((ls) => ls.map((l) => (l.id === line.id ? { ...l, recorded: true } : l)))
        } catch (e: any) { setError(String(e).slice(0, 200)) }
        setBusy(null)
      }
      mr.start()
      recorder.current = mr
      setBusy(line.id)
    } catch {
      setError('No microphone available.')
      setBusy(null)
    }
  }

  const stop = () => recorder.current?.stop()
  const done = lines.filter((l) => l.recorded).length

  return (
    <div className="wrap">
      <div className="panel">
        <h2>Record the evaluation set</h2>
        <p className="muted">
          The evaluation audio is currently rendered with Piper, so the Hindi,
          Marathi and code-mixed error rates measure a synthesiser transcribing
          its own output rather than speech recognition. Reading these lines
          aloud replaces that with a real number. Use the laptop microphone you
          will demo with, not a studio mic: the point is to measure what the
          system will actually hear.
        </p>
        <div className="row">
          {LANGS.map((l) => (
            <button key={l.code} className={lang === l.code ? '' : 'secondary'}
                    onClick={() => setLang(l.code)}>{l.label}</button>
          ))}
        </div>
        <p className="muted" data-testid="progress">
          {done} of {lines.length} recorded.
          {lines.length > 0 && lines.length < 30 &&
            ` The latency harness wants 30 per language, so this path still repeats clips.`}
        </p>
        {note && <p style={{ color: 'var(--green)' }}>{note}</p>}
        {error && <p style={{ color: 'var(--red)' }} data-testid="error">{error}</p>}
      </div>

      <div className="panel">
        <table>
          <thead><tr><th>id</th><th>say this</th><th>intent</th><th /></tr></thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.id}>
                <td className="mono">{l.id}</td>
                <td>{l.text}</td>
                <td className="muted">{l.intent}</td>
                <td>
                  {busy === l.id
                    ? <button className="danger" onClick={stop}>Stop</button>
                    : <button className="secondary" disabled={!!busy}
                              data-testid={`rec-${l.id}`}
                              onClick={() => record(l)}>
                        {l.recorded ? 'Re-record' : 'Record'}
                      </button>}
                  {l.recorded && (
                    playing[l.id]
                      ? <audio controls src={playing[l.id]} style={{ height: 32, marginLeft: 6, verticalAlign: 'middle' }} />
                      : <button className="secondary" style={{ marginLeft: 6 }}
                                data-testid={`play-${l.id}`}
                                onClick={() => play(l.id)}>Play</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {lines.length === 0 && <p className="muted">Nothing to record.</p>}
      </div>
    </div>
  )
}
