import { useEffect, useState } from 'react'
import { api, type CallDetail, type CallFilters, type CallRow, type Trace } from '../api'
import TraceView from '../components/TraceView'
import LedgerPanel from '../components/LedgerPanel'
import CapabilityLegend from '../components/CapabilityLegend'

// The compliance officer's view. Everything here is a query over stored
// traces and the ledger, never a reconstruction after the fact.
//
// The lookup this replaces answered 200 with an empty list for an unknown id,
// a partial id, a customer id and a typo alike, so nothing a user typed could
// report failure and the panel just stayed blank. See DECISIONS.md D22. The
// rules now: a miss says so, a leading fragment of an id is enough, and the
// recent calls list means nobody has to type an identifier at all.

// 'interrupted' is not a decision but a property of a turn. It sits in the
// same list because it answers the same question: show me the calls where
// this happened.
const DECISIONS = ['', 'automated', 'clarify', 'refused', 'escalated',
                   'superseded', 'interrupted']
const LANGS = ['', 'en', 'hi', 'mr']

export default function Compliance() {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<CallFilters>({})
  const [calls, setCalls] = useState<CallRow[]>([])
  const [detail, setDetail] = useState<CallDetail | null>(null)
  const [selected, setSelected] = useState<Trace | null>(null)
  const [audio, setAudio] = useState<Record<string, string>>({})
  const [handovers, setHandovers] = useState<any[]>([])
  const [metrics, setMetrics] = useState<any>(null)
  const [kb, setKb] = useState<any[]>([])
  const [access, setAccess] = useState<any[]>([])
  const [provs, setProvs] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'calls' | 'ledger' | 'queue' | 'access' | 'system'>('calls')

  const refresh = async () => {
    try {
      const [h, m] = await Promise.all([api.handovers(), api.metrics()])
      setHandovers(h.handovers); setMetrics(m)
    } catch (e: any) { setError(String(e)) }
  }
  useEffect(() => {
    refresh()
    api.kb().then((d) => setKb(d.documents)).catch(() => {})
    api.providers().then(setProvs).catch(() => {})
    loadCalls({})
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const loadCalls = async (f: CallFilters) => {
    setError(null); setBusy(true)
    try {
      const out = await api.calls(f)
      setCalls(out.calls)
      setNote(out.count === 0 ? 'No calls match those filters.' : `${out.count} call${out.count === 1 ? '' : 's'}.`)
    } catch (e: any) { setError(String(e)) }
    setBusy(false)
  }

  const openCall = async (callId: string) => {
    setError(null); setBusy(true); setAudio({})
    try {
      const d = await api.call(callId)
      setDetail(d)
      setSelected(d.traces[d.traces.length - 1] ?? null)
      setTab('calls')
    } catch (e: any) { setError(String(e)) }
    setBusy(false)
  }

  // One box. Call id, session id, customer id, case id or registered mobile,
  // any of them by a leading fragment.
  const lookup = async () => {
    const q = query.trim()
    if (!q) return
    setError(null); setNote(null); setBusy(true)
    try {
      const hit = await api.resolve(q)
      if (hit.kind === 'call') { await openCall(hit.id) }
      else if (hit.kind === 'session' && hit.call_id) {
        setNote(`Session ${hit.id.slice(0, 8)} belongs to call ${hit.call_id}.`)
        await openCall(hit.call_id)
      } else if (hit.kind === 'customer') {
        setFilters({ customer_id: hit.id }); setDetail(null)
        await loadCalls({ customer_id: hit.id })
        setNote(`Customer ${hit.id}.`)
      } else if (hit.kind === 'case') {
        const cs = await api.cases()
        const found = cs.cases.find((c: any) => c.case_id === hit.id)
        if (found?.call_id) { setNote(`Case ${hit.id} on call ${found.call_id}.`); await openCall(found.call_id) }
        else setNote(`Case ${hit.id} is not attached to a call.`)
      }
    } catch (e: any) {
      // A 404 here carries the message that says what can be searched for.
      setError(String(e).replace(/^Error:\s*/, ''))
      setDetail(null)
    }
    setBusy(false)
  }

  const play = async (recordingId: string) => {
    setError(null)
    try {
      setAudio((a) => ({ ...a, [recordingId]: '' }))
      const url = await api.recordingUrl(recordingId)
      setAudio((a) => ({ ...a, [recordingId]: url }))
    } catch (e: any) {
      setAudio((a) => { const n = { ...a }; delete n[recordingId]; return n })
      setError('Playback refused: ' + String(e).slice(0, 220))
    }
  }

  const setFilter = (k: keyof CallFilters, v: string) =>
    setFilters((f) => ({ ...f, [k]: v || undefined }))

  const brokenRecords = (detail?.ledger || []).filter((r) => !r.verified).length

  return (
    <div className="wrap">
      <div className="panel">
        <div className="row">
          <input placeholder="call id, session id, customer id, case id or mobile (a leading part is enough)"
                 value={query} onChange={(e) => setQuery(e.target.value)}
                 data-testid="lookup"
                 onKeyDown={(e) => { if (e.key === 'Enter') lookup() }} />
          <button onClick={lookup} disabled={busy} data-testid="lookup-go">Look up</button>
          <button className="secondary" onClick={() => setTab('calls')}>Calls</button>
          <button className="secondary" onClick={() => setTab('ledger')}>Ledger</button>
          <button className="secondary" onClick={() => setTab('queue')}>Escalation queue</button>
          <button className="secondary" onClick={() => {
            setTab('access'); api.accessLog().then((d) => setAccess(d.entries)).catch(() => {})
          }}>Access log</button>
          <button className="secondary" onClick={() => setTab('system')}>System</button>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <input type="date" value={filters.date_from || ''} onChange={(e) => setFilter('date_from', e.target.value)} />
          <input type="date" value={filters.date_to || ''} onChange={(e) => setFilter('date_to', e.target.value)} />
          <select value={filters.decision || ''} onChange={(e) => setFilter('decision', e.target.value)}>
            {DECISIONS.map((d) => <option key={d} value={d}>{d || 'any decision'}</option>)}
          </select>
          <select value={String(filters.tier ?? '')} onChange={(e) => setFilter('tier', e.target.value)}>
            <option value="">any tier</option>
            {[0, 1, 2, 3].map((t) => <option key={t} value={t}>tier {t} or above</option>)}
          </select>
          <select value={filters.language || ''} onChange={(e) => setFilter('language', e.target.value)}>
            {LANGS.map((l) => <option key={l} value={l}>{l || 'any language'}</option>)}
          </select>
          <button onClick={() => { setDetail(null); loadCalls(filters) }} disabled={busy}>Apply</button>
          <button className="secondary" onClick={() => {
            setFilters({}); setQuery(''); setDetail(null); loadCalls({})
          }}>Recent calls</button>
        </div>
        {note && <p className="muted" data-testid="note">{note}</p>}
        {error && <p style={{ color: 'var(--red)' }} data-testid="error">{error}</p>}
      </div>

      {tab === 'calls' && (
        <div className="cols" style={{ gridTemplateColumns: '340px 1fr' }}>
          <div className="panel">
            <h2>Calls</h2>
            {calls.length === 0 && <p className="muted">Nothing to show.</p>}
            <table data-testid="calls">
              <tbody>
                {calls.map((c) => (
                  <tr key={c.call_id} style={{ cursor: 'pointer' }}
                      data-testid={`call-${c.call_id}`} onClick={() => openCall(c.call_id)}>
                    <td>
                      <span className="mono">{c.call_id}</span>
                      {c.max_tier != null && <span className="pill" style={{ marginLeft: 6 }}>tier {c.max_tier}</span>}
                      <br />
                      <span className="muted">
                        {c.customer_id || 'unidentified'}
                        {c.customer_name ? ` (${c.customer_name})` : ''}
                        {' | '}{String(c.started_at).slice(0, 16).replace('T', ' ')}
                        {' | '}{c.turns} turn{c.turns === 1 ? '' : 's'}
                        {c.recordings ? ` | ${c.recordings} recording${c.recordings === 1 ? '' : 's'}` : ''}
                        {c.cases ? ` | ${c.cases} case${c.cases === 1 ? '' : 's'}` : ''}
                        {c.interrupted ? ` | ${c.interrupted} interrupted` : ''}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            {!detail && <div className="panel"><p className="muted">Pick a call, or look one up above.</p></div>}
            {detail && (
              <>
                <div className="panel" data-testid="call-detail">
                  <h2>Call {detail.call.call_id}</h2>
                  <p className="muted">
                    {detail.call.customer_id
                      ? `${detail.call.customer_id}${detail.customer?.name ? ` (${detail.customer.name})` : ''}`
                      : 'never identified'}
                    {' | '}{detail.call.channel}
                    {' | '}started {String(detail.call.started_at).replace('T', ' ').slice(0, 19)}
                    {' | '}{detail.call.language || 'language not set'}
                    {' | '}recording consent {detail.call.recording_consent ? 'given' : 'not given'}
                  </p>
                  <div className="row" style={{ flexWrap: 'wrap' }}>
                    {detail.turns.map((t: any) => (
                      <button key={t.turn_id} className="secondary"
                              data-testid={`turn-${t.turn_id}`}
                              onClick={() => setSelected(detail.traces.find(
                                (x) => x.trace_id === t.trace_id) ?? null)}>
                        turn {t.turn_id}{' '}
                        <span className={'pill ' + (t.decision || '')}>{t.decision || 'no decision'}</span>
                        {t.risk_tier != null && ` tier ${t.risk_tier}`}
                        {t.interrupted ? ' interrupted' : ''}
                      </button>
                    ))}
                  </div>
                </div>

                {detail.cases.length > 0 && (
                  <div className="panel">
                    <h3>Cases</h3>
                    <table>
                      <thead><tr><th>case</th><th>reason</th><th>status</th><th>agent</th><th>outcome</th></tr></thead>
                      <tbody>
                        {detail.cases.map((c: any) => (
                          <tr key={c.case_id}>
                            <td className="mono">{c.case_id}</td><td>{c.reason}</td>
                            <td>{c.status}</td><td>{c.assigned_agent || ''}</td>
                            <td>{c.outcome || ''}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="panel">
                  <h3>Recordings</h3>
                  {detail.recordings.length === 0 && (
                    <p className="muted">
                      No audio kept for this call. Recording starts only after the spoken
                      notice and an explicit yes, so this is the ordinary case.
                    </p>
                  )}
                  {detail.recordings.map((r) => (
                    <div key={r.recording_id} style={{ marginBottom: 8 }}>
                      <span className="mono">{r.recording_id}</span>{' '}
                      <span className="muted">
                        {r.speaker}
                        {r.turn_id != null ? ` | turn ${r.turn_id}` : ''}
                        {r.duration_s ? ` | ${r.duration_s.toFixed(1)}s` : ''}
                        {' | keep until '}{String(r.retention_until).slice(0, 10)}
                      </span>
                      {r.purged_at
                        ? <span className="pill refused" style={{ marginLeft: 6 }}>purged {String(r.purged_at).slice(0, 10)}</span>
                        : audio[r.recording_id]
                          ? <audio controls src={audio[r.recording_id]} style={{ display: 'block', marginTop: 4 }} />
                          : <button className="secondary" style={{ marginLeft: 6 }}
                                    data-testid={`play-${r.recording_id}`}
                                    onClick={() => play(r.recording_id)}>Play</button>}
                    </div>
                  ))}
                  <p className="muted">
                    Playback decrypts the file and checks it against the digest taken when
                    it was written. Every play is appended to the ledger as an access event.
                  </p>
                </div>

                <div className="panel">
                  <h3>
                    Ledger records for this call{' '}
                    <span className={'pill ' + (brokenRecords ? 'refused' : 'automated')}
                          data-testid="ledger-status">
                      {brokenRecords ? `${brokenRecords} broken` : 'all verified'}
                    </span>
                  </h3>
                  <table>
                    <thead><tr><th>#</th><th>kind</th><th>when</th><th>check</th></tr></thead>
                    <tbody>
                      {detail.ledger.map((r) => (
                        <tr key={r.idx}>
                          <td className="mono">{r.idx}</td>
                          <td>{r.kind}</td>
                          <td className="mono">{String(r.ts).slice(11, 19)}</td>
                          <td className={r.verified ? '' : 'mono'}
                              style={{ color: r.verified ? 'var(--green)' : 'var(--red)' }}>
                            {r.verified ? 'intact' : `broken: ${r.reason}`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted">
                    Each record is re-checked now, not trusted. A record can pass here while
                    the chain is broken further back, so run a full verify on the Ledger tab
                    as well.
                  </p>
                </div>

                {selected && <TraceView trace={selected} />}
              </>
            )}
          </div>
        </div>
      )}

      {tab === 'ledger' && <LedgerPanel />}

      {tab === 'access' && (
        <div className="panel">
          <h2>Access log</h2>
          <p className="muted">
            Every search, every call opened and every recording played by an officer,
            written to the access log and appended to the ledger. An audit trail that
            does not record its own auditors is half a trail.
          </p>
          <table>
            <thead><tr><th>when</th><th>actor</th><th>role</th><th>action</th><th>target</th><th>detail</th></tr></thead>
            <tbody>
              {access.map((a) => (
                <tr key={a.access_id}>
                  <td className="mono">{String(a.at).slice(11, 19)}</td>
                  <td>{a.actor}</td><td>{a.role}</td><td>{a.action}</td>
                  <td className="mono">{a.target_id || a.target_type || ''}</td>
                  <td className="muted">{a.detail || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {access.length === 0 && <p className="muted">Nothing logged yet.</p>}
        </div>
      )}

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
                    setNote('Context packet received for ' + String(h.trace_id).slice(0, 8) +
                            '. It carries the whole conversation, redacted.')
                    console.log('handover packet', out.packet)
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
          <div>
          <div className="panel">
            <h2>Speech providers</h2>
            <p className="muted">
              Which engine answers for each language, and what it has cost.
              These APIs bill per use, so the meter is on screen rather than
              discovered on an invoice.
            </p>
            {provs ? (
              <>
                <table>
                  <thead><tr><th>provider</th><th>state</th><th>leaves machine</th></tr></thead>
                  <tbody>
                    {Object.entries(provs.tts || {}).map(([name, h]: any) => (
                      <tr key={name}>
                        <td className="mono">{name}</td>
                        <td className={h.available ? '' : 'muted'}>
                          {h.available ? 'available' : h.reason}
                        </td>
                        <td>{h.leaves_machine
                          ? <span className="tag SIMULATED">yes</span>
                          : <span className="pill automated">no</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mono" style={{ fontSize: 13 }}>
                  speaking: {Object.entries(provs.selected || {})
                    .map(([l, n]) => `${l} ${n}`).join(' | ')}
                </p>
                {Object.keys(provs.usage || {}).length > 0 && (
                  <table>
                    <thead><tr><th>provider</th><th>characters spoken</th><th>audio seconds</th><th>calls</th><th>fallbacks</th></tr></thead>
                    <tbody>
                      {Object.entries(provs.usage).map(([name, u]: any) => (
                        <tr key={name}>
                          <td className="mono">{name}</td>
                          <td>{u.characters_synthesised}</td>
                          <td>{u.audio_seconds_transcribed}</td>
                          <td>{u.calls}</td>
                          <td>{u.fallbacks}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : <p className="muted">No provider information.</p>}
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
        </div>
      )}
    </div>
  )
}
