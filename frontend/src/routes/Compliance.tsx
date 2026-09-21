import { useEffect, useState } from 'react'
import { api, type Trace } from '../api'
import TraceView from '../components/TraceView'
import LedgerPanel from '../components/LedgerPanel'
import CapabilityLegend from '../components/CapabilityLegend'

// The compliance officer's view. Everything here is a query over stored
// traces and the ledger, never a reconstruction after the fact.

export default function Compliance() {
  const [sessionId, setSessionId] = useState('')
  const [traces, setTraces] = useState<Trace[]>([])
  const [selected, setSelected] = useState<Trace | null>(null)
  const [handovers, setHandovers] = useState<any[]>([])
  const [metrics, setMetrics] = useState<any>(null)
  const [kb, setKb] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'trace' | 'ledger' | 'queue' | 'system'>('trace')

  const refresh = async () => {
    try {
      const [h, m] = await Promise.all([api.handovers(), api.metrics()])
      setHandovers(h.handovers); setMetrics(m)
    } catch (e: any) { setError(String(e)) }
  }
  useEffect(() => {
    refresh()
    api.kb().then((d) => setKb(d.documents)).catch(() => {})
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const loadSession = async (id: string) => {
    setError(null)
    try {
      const out = await api.sessionTraces(id.trim())
      setTraces(out.traces)
      setSelected(out.traces[out.traces.length - 1] ?? null)
      setTab('trace')
    } catch (e: any) { setError(String(e)) }
  }

  return (
    <div className="wrap">
      <div className="panel">
        <div className="row">
          <input placeholder="session id, or paste one from the customer console"
                 value={sessionId} onChange={(e) => setSessionId(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') loadSession(sessionId) }} />
          <button onClick={() => loadSession(sessionId)}>Load session</button>
          <button className="secondary" onClick={() => setTab('trace')}>Trace</button>
          <button className="secondary" onClick={() => setTab('ledger')}>Ledger</button>
          <button className="secondary" onClick={() => setTab('queue')}>Escalation queue</button>
          <button className="secondary" onClick={() => setTab('system')}>System</button>
        </div>
        {error && <p style={{ color: 'var(--red)' }}>{error}</p>}
      </div>

      {tab === 'trace' && (
        <div className="cols" style={{ gridTemplateColumns: '300px 1fr' }}>
          <div className="panel">
            <h2>Turns in this session</h2>
            {traces.length === 0 && <p className="muted">Load a session id to see its turns.</p>}
            {traces.map((t) => (
              <div key={t.trace_id} style={{ marginBottom: 6 }}>
                <button className="secondary" style={{ width: '100%', textAlign: 'left' }}
                        onClick={() => setSelected(t)}>
                  <strong>turn {t.turn_index}</strong>{' '}
                  <span className={'pill ' + (t.decision || '')}>{t.decision}</span>
                  <br /><span className="muted">{(t.transcript || '').slice(0, 52)}</span>
                </button>
              </div>
            ))}
          </div>
          <div>{selected ? <TraceView trace={selected} /> :
            <div className="panel"><p className="muted">No turn selected.</p></div>}</div>
        </div>
      )}

      {tab === 'ledger' && <LedgerPanel />}

      {tab === 'queue' && (
        <div className="panel">
          <h2>Escalation queue <span className="tag SIMULATED">SIMULATED agent console</span></h2>
          <table>
            <thead><tr><th>handover</th><th>trace</th><th>raised</th><th>reason</th><th>status</th><th /></tr></thead>
            <tbody>
              {handovers.map((h) => (
                <tr key={h.handover_id}>
                  <td className="mono">{h.handover_id}</td>
                  <td className="mono">{String(h.trace_id).slice(0, 8)}</td>
                  <td className="mono">{String(h.created_at).slice(11, 19)}</td>
                  <td>{h.reason}</td>
                  <td>{h.status}{h.claimed_by ? ` by ${h.claimed_by}` : ''}</td>
                  <td><button className="secondary" onClick={async () => {
                    const out = await api.claimHandover(h.trace_id)
                    alert('Context packet received:\n\n' + JSON.stringify(out.packet, null, 2).slice(0, 1400))
                    refresh()
                  }}>Claim</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {handovers.length === 0 && <p className="muted">Nothing queued.</p>}
          <p className="muted">
            The packet carries the whole conversation so the customer does not repeat
            themselves, and it is redacted: the agent sees tokens, not identifiers.
          </p>
        </div>
      )}

      {tab === 'system' && (
        <div className="cols">
          <div>
            <CapabilityLegend />
            <div className="panel">
              <h2>Policy knowledge base</h2>
              <table>
                <thead><tr><th>doc</th><th>ver</th><th>effective</th><th>title</th></tr></thead>
                <tbody>
                  {kb.map((d) => (
                    <tr key={d.doc_id + d.version}>
                      <td className="mono">{d.doc_id}</td>
                      <td className="mono">{d.version}{d.superseded_by ? ' (superseded)' : ''}</td>
                      <td className="mono">{d.effective_date}</td>
                      <td>{d.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                Two versions of POL-HL-001 are seeded deliberately, so a citation can be shown
                to name the version it used and exclude the superseded one.
              </p>
            </div>
          </div>
          <div className="panel">
            <h2>Latency and decisions</h2>
            {metrics ? (
              <>
                <p>
                  {metrics.turns} turns.{' '}
                  {Object.entries(metrics.decisions || {}).map(([k, v]: any) => (
                    <span key={k} className={'pill ' + k} style={{ marginRight: 6 }}>{k} {v}</span>
                  ))}
                </p>
                <table>
                  <thead><tr><th>stage</th><th>n</th><th>p50 ms</th><th>p95 ms</th></tr></thead>
                  <tbody>
                    {Object.entries(metrics.stages || {}).map(([name, s]: any) => (
                      <tr key={name}><td className="mono">{name}</td><td>{s.n}</td><td>{s.p50_ms}</td><td>{s.p95_ms}</td></tr>
                    ))}
                  </tbody>
                </table>
                <h3>Ledger records by kind</h3>
                <p className="mono">{JSON.stringify(metrics.ledger_records_by_kind)}</p>
              </>
            ) : <p className="muted">No metrics yet.</p>}
            <p className="muted">
              These are read off the trace timings, not a separate metrics pipeline.
              Prometheus and Grafana are the production substitution.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
