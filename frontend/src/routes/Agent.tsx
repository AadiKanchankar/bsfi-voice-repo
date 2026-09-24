import { useEffect, useState } from 'react'
import { api } from '../api'

// R6. The agent console.
//
// A real helpline does not go silent when it transfers you, and the person
// who picks up should not have to ask everything again. This screen exists
// so that the context the assistant already gathered actually reaches them:
// the plain-language reason, the intake answers, the risk reasoning, and the
// redacted transcript.
//
// The agent types; the caller hears it in their own language through the
// same normaliser and voice as everything else, so an agent typing an amount
// gets it read in the Indian system without having to know that.

export default function Agent() {
  const [cases, setCases] = useState<any[]>([])
  const [packet, setPacket] = useState<any>(null)
  const [reply, setReply] = useState('')
  const [outcome, setOutcome] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const agentId = 'AGENT1'

  const refresh = async () => {
    try { setCases((await api.agentQueue()).cases) }
    catch (e: any) { setError(String(e).slice(0, 200)) }
  }
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const accept = async (caseId: string) => {
    setError(null)
    try {
      setPacket(await api.acceptCase(caseId, agentId))
      setNote(`Accepted ${caseId}.`)
      refresh()
    } catch (e: any) { setError(String(e).slice(0, 200)) }
  }

  const say = async () => {
    if (!packet || !reply.trim()) return
    try {
      await api.agentReply(packet.case.case_id, agentId, reply,
                           packet.case.language || 'en')
      setNote(`Spoken to the caller: ${reply}`)
      setReply('')
    } catch (e: any) { setError(String(e).slice(0, 200)) }
  }

  const close = async () => {
    if (!packet || !outcome.trim()) return
    try {
      await api.closeCase(packet.case.case_id, agentId, outcome)
      setNote(`Closed ${packet.case.case_id}: ${outcome}`)
      setPacket(null); setOutcome(''); refresh()
    } catch (e: any) { setError(String(e).slice(0, 200)) }
  }

  return (
    <div className="wrap cols" style={{ gridTemplateColumns: '320px 1fr' }}>
      <div className="panel">
        <h2>Queue <span className="tag SIMULATED">SIMULATED agent</span></h2>
        <p className="muted">
          Cases the assistant escalated. It stayed on the line and gathered
          what you would have asked for.
        </p>
        {cases.length === 0 && <p className="muted">Nothing waiting.</p>}
        <table data-testid="queue">
          <tbody>
            {cases.map((c) => (
              <tr key={c.case_id}>
                <td>
                  <span className="mono">{c.case_id}</span><br />
                  <span className="muted">
                    {c.reason} | {c.customer_id || 'unidentified'}
                    {c.customer_name ? ` (${c.customer_name})` : ''}
                  </span>
                </td>
                <td>
                  <button className="secondary" data-testid={`accept-${c.case_id}`}
                          onClick={() => accept(c.case_id)}>Accept</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {note && <p style={{ color: 'var(--green)' }} data-testid="note">{note}</p>}
        {error && <p style={{ color: 'var(--red)' }} data-testid="error">{error}</p>}
      </div>

      <div>
        {!packet && <div className="panel"><p className="muted">Accept a case to see its context.</p></div>}
        {packet && (
          <>
            <div className="panel" data-testid="packet">
              <h2>{packet.case.case_id} <span className="pill">{packet.case.reason}</span></h2>
              <p className="muted">
                {packet.case.customer_id || 'unidentified caller'}
                {' | opened '}{String(packet.case.created_at).replace('T', ' ').slice(0, 19)}
              </p>

              <h3>What the caller already told us</h3>
              {Object.keys(packet.intake || {}).length === 0
                ? <p className="muted">Nothing recorded.</p>
                : (
                  <table>
                    <tbody>
                      {Object.entries(packet.intake).map(([k, v]: any) => (
                        <tr key={k}><td className="mono">{k}</td><td>{String(v)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              <p className="muted">
                Do not ask these again. The point of collecting them was to
                save the caller repeating themselves.
              </p>
            </div>

            {packet.traces && packet.traces.length > 0 && (
              <div className="panel">
                <h3>The conversation, redacted</h3>
                <table>
                  <thead><tr><th>turn</th><th>said</th><th>intent</th><th>tier</th><th>decision</th></tr></thead>
                  <tbody>
                    {packet.traces.map((t: any, i: number) => (
                      <tr key={i}>
                        <td>{t.turn}</td>
                        <td>{t.transcript}</td>
                        <td className="muted">{t.intent}</td>
                        <td>{t.risk_tier}</td>
                        <td><span className={'pill ' + (t.decision || '')}>{t.decision}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted">
                  Identifiers are tokens, not values. You are seeing what the
                  compliance record sees.
                </p>
              </div>
            )}

            <div className="panel">
              <h3>Speak to the caller</h3>
              <div className="row">
                <input value={reply} onChange={(e) => setReply(e.target.value)}
                       data-testid="agent-reply"
                       placeholder="Type, and the caller hears it in their language"
                       onKeyDown={(e) => { if (e.key === 'Enter') say() }} />
                <button onClick={say} disabled={!reply.trim()}>Say it</button>
              </div>
              <p className="muted">
                Goes through the same normaliser as everything else, so an
                amount you type is read in the Indian system and a code is
                spelled out.
              </p>

              <h3>Close the case</h3>
              <div className="row">
                <input value={outcome} onChange={(e) => setOutcome(e.target.value)}
                       data-testid="outcome" placeholder="What was the outcome?" />
                <button className="danger" onClick={close}
                        disabled={!outcome.trim()}>Close</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
