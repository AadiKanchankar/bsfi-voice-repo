import type { Trace } from '../api'

// Renders one ComplianceTrace end to end. Everything on this screen comes out
// of the trace object: nothing is recomputed in the browser, because the claim
// being demonstrated is that the trace alone is enough to explain the decision.

const pct = (v: number | null | undefined) => (v == null ? 'n/a' : (v * 100).toFixed(1) + '%')
const num = (v: number | null | undefined, d = 3) => (v == null ? 'n/a' : v.toFixed(d))

export function CapabilityTag({ status }: { status: string }) {
  return <span className={'tag ' + status}>{status}</span>
}

export function StageTimeline({ trace }: { trace: Trace }) {
  const total = trace.stages.reduce((a, s) => a + s.duration_ms, 0)
  return (
    <div className="panel">
      <h2>Stage timeline, {total.toFixed(0)} ms total</h2>
      <div className="stagebar">
        {trace.stages.map((s, i) => (
          <div key={i} className={'stage ' + s.capability} title={s.notes || ''}>
            <div><strong>{s.stage}</strong> <CapabilityTag status={s.capability} /></div>
            <div className="ms">{s.duration_ms.toFixed(1)} ms{s.confidence != null ? ` | conf ${num(s.confidence)}` : ''}</div>
            {s.model_id && <div className="ms">{s.model_id}</div>}
            {s.notes && <div className="ms" style={{ color: 'var(--amber)' }}>{s.notes}</div>}
          </div>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        Each stage records the SHA-256 digest of its input, never the input itself. Stages
        marked SIMULATED or BASELINE are not claiming to be the production component.
      </p>
    </div>
  )
}

export function LanguagePanel({ trace }: { trace: Trace }) {
  if (!trace.language_spans.length) return null
  return (
    <div className="panel">
      <h2>Language identification, code-mix index {trace.code_mix_index ?? 0}</h2>
      <div>
        {trace.language_spans.map((s, i) => (
          <span key={i} className={'spanchip ' + s.lang}>
            <strong>{s.lang}</strong> {s.text} <span className="muted">({num(s.confidence, 2)})</span>
          </span>
        ))}
      </div>
      <p className="muted">
        Spans are the output of Viterbi smoothing over per-word posteriors with a switch
        penalty, so the tagger reports coherent runs instead of alternating labels.
        CMI 0 means monolingual. Dominant language: <strong>{trace.dominant_language}</strong>,
        which is also the language the reply was spoken in.
      </p>
    </div>
  )
}

export function RiskPanel({ trace }: { trace: Trace }) {
  const c = trace.risk_components || {}
  const raw = c.raw || {}
  const weights = c.weights || {}
  const weighted = c.weighted || {}
  const tiering = c.tiering || {}
  const labels: Record<string, string> = {
    sens: 'sens(intent)', amount: 'norm(amount)', verify: '1 - s_verify', history: 'dev(history)',
  }
  return (
    <div className="panel">
      <h2>Risk score and tier</h2>
      <div className="row" style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 30, fontWeight: 800 }}>R = {num(trace.risk_score)}</div>
        <span className={'pill tier' + (trace.risk_tier ?? 0)}>tier {trace.risk_tier}</span>
        {trace.tier_overridden && <span className="pill tier3">hard override</span>}
        {trace.tier_ratcheted && <span className="pill tier2">session ratchet</span>}
      </div>
      <table>
        <thead><tr><th>term</th><th>raw</th><th>weight</th><th>contribution</th><th></th></tr></thead>
        <tbody>
          {Object.keys(labels).map((k) => (
            <tr key={k}>
              <td>{labels[k]}</td>
              <td className="mono">{num(raw[k])}</td>
              <td className="mono">{weights[k]}</td>
              <td className="mono">{num(weighted[k])}</td>
              <td style={{ width: 160 }}>
                <div className="bar"><span style={{ width: `${Math.min(100, (weighted[k] || 0) * 250)}%` }} /></div>
              </td>
            </tr>
          ))}
          <tr><td><strong>R</strong></td><td colSpan={3} className="mono"><strong>{num(trace.risk_score)}</strong></td><td /></tr>
        </tbody>
      </table>
      <p className="muted">
        Cut-points {JSON.stringify(tiering.cutpoints ?? [0.25, 0.5, 0.75])}. Scored tier{' '}
        {tiering.scored_tier ?? 'n/a'}, session floor {tiering.session_floor ?? 0}, applied tier{' '}
        {trace.risk_tier}. Anomalies counted: {(c.inputs?.anomalies || []).join(', ') || 'none'}.
        Confidence required at this tier, tau = {trace.tau_required}.
      </p>
      <h3>Confidence fusion</h3>
      <p className="mono" style={{ fontSize: 13 }}>
        c_final = c_asr^{trace.fusion_weights?.alpha} x c_intent^{trace.fusion_weights?.beta} x
        {' '}c_retr^{trace.fusion_weights?.gamma} = {num(trace.fused_confidence)}
      </p>
      <p className="muted">
        c_asr {num(trace.asr_confidence)}, c_intent {num(trace.intent_confidence)}. Geometric,
        so one weak signal can veto automation on its own.
      </p>
    </div>
  )
}

export function RetrievalPanel({ trace }: { trace: Trace }) {
  const stage = trace.stages.find((s) => s.stage === 'retrieval')
  if (!stage) return null
  const grounded = trace.retrieved.length > 0
  return (
    <div className="panel">
      <h2>Retrieval grounding</h2>
      <p>
        Max similarity <strong className="mono">{num(trace.retrieval_max_score)}</strong> against
        floor delta <strong className="mono">{num(trace.retrieval_floor, 2)}</strong>{' '}
        {grounded ? <span className="pill automated">above the floor</span>
                  : <span className="pill refused">below the floor, refusing</span>}
      </p>
      {grounded ? (
        <table>
          <thead><tr><th>document</th><th>version</th><th>effective</th><th>section</th><th>score</th></tr></thead>
          <tbody>
            {trace.retrieved.map((p, i) => (
              <tr key={i}>
                <td className="mono">{p.doc_id}</td>
                <td className="mono"><strong>{p.version}</strong></td>
                <td className="mono">{p.effective_date}</td>
                <td>{p.section}</td>
                <td className="mono">{p.score.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">
          Nothing cleared the floor, so no answer was generated. The assistant declined and
          offered a human. Silence is an acceptable outcome; a confident wrong answer about a
          customer's money is not.
        </p>
      )}
      {stage.outputs?.superseded_versions?.length > 0 && (
        <p className="muted">
          Superseded versions matched and were excluded from the answer:{' '}
          {stage.outputs.superseded_versions.map((s: any) => `${s.doc_id} v${s.version}`).join(', ')}
        </p>
      )}
    </div>
  )
}

export function AuthPanel({ trace }: { trace: Trace }) {
  const a = trace.auth
  if (!a) return null
  return (
    <div className="panel">
      <h2>Authentication</h2>
      <table>
        <tbody>
          <tr><td>method</td><td className="mono">{a.method}</td></tr>
          <tr><td>speaker cosine</td><td className="mono">{num(a.speaker_score, 4)} against theta {num(a.threshold, 3)}</td></tr>
          <tr><td>anti-spoof score <span className="tag BASELINE">BASELINE</span></td><td className="mono">{num(a.spoof_score, 4)}</td></tr>
          <tr><td>s_verify = cosine x spoof</td><td className="mono">{num(a.s_verify, 4)}</td></tr>
          <tr><td>passed</td><td>{a.passed ? <span className="pill automated">yes</span> : <span className="pill escalated">no</span>}</td></tr>
          {a.otp_required && <tr><td>one time password <span className="tag SIMULATED">SIMULATED</span></td>
            <td>{a.otp_passed == null ? 'requested' : a.otp_passed ? 'accepted' : 'rejected'}</td></tr>}
          {a.readback_text && <tr><td>spoken read-back</td><td>{a.readback_text} {a.readback_confirmed ? '(confirmed)' : '(awaiting confirmation)'}</td></tr>}
          {a.reason && <tr><td>reason</td><td>{a.reason}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export function DecisionPanel({ trace }: { trace: Trace }) {
  const policy = trace.stages.find((s) => s.stage === 'policy')
  return (
    <div className="panel">
      <h2>Decision</h2>
      <p style={{ fontSize: 18 }}>
        <span className={'pill ' + (trace.decision || '')}>{trace.decision}</span>{' '}
        <strong>{trace.action_taken}</strong>
      </p>
      <p>{trace.decision_reason}</p>
      {policy?.outputs?.checks && (
        <table>
          <thead><tr><th>condition</th><th>result</th><th>detail</th></tr></thead>
          <tbody>
            {policy.outputs.checks.map((c: any, i: number) => (
              <tr key={i}>
                <td className="mono">{c.check}</td>
                <td>{c.passed ? <span className="pill automated">pass</span> : <span className="pill escalated">fail</span>}</td>
                <td className="muted">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {trace.handover_packet_ref && (
        <p className="muted">Handover packet <span className="mono">{trace.handover_packet_ref}</span> queued for an agent.</p>
      )}
    </div>
  )
}

export function PiiPanel({ trace }: { trace: Trace }) {
  const tokens = Object.entries(trace.pii_tokens || {})
  return (
    <div className="panel">
      <h2>Stored transcript and PII</h2>
      <p className="mono" style={{ background: '#f2f4f7', padding: 8, borderRadius: 6 }}>
        {trace.transcript || '(empty)'}
      </p>
      {tokens.length > 0 ? (
        <>
          <table>
            <thead><tr><th>token</th><th>type</th><th>value</th></tr></thead>
            <tbody>
              {tokens.map(([t, ty]) => (
                <tr key={t}><td className="mono">{t}</td><td>{ty}</td>
                  <td className="muted">held encrypted in the session vault, not readable here</td></tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Identifiers were tokenised before this transcript reached disk. The raw values sit in
            a per-session AES-256-GCM vault in a separate table, and consent withdrawal deletes it.
          </p>
        </>
      ) : <p className="muted">No identifiers were detected in this turn.</p>}
      <p className="muted">Raw audio was dropped from memory as soon as transcription finished. Nothing was written to disk.</p>
    </div>
  )
}

export default function TraceView({ trace }: { trace: Trace }) {
  return (
    <div>
      <div className="panel">
        <h2>Turn {trace.turn_index} | trace {trace.trace_id.slice(0, 8)}</h2>
        <p><strong>Intent</strong> <span className="mono">{trace.intent}</span> at {pct(trace.intent_confidence)}
          {Object.keys(trace.slots || {}).length > 0 && <> | <strong>slots</strong> <span className="mono">{JSON.stringify(trace.slots)}</span></>}
        </p>
      </div>
      <StageTimeline trace={trace} />
      <LanguagePanel trace={trace} />
      <RetrievalPanel trace={trace} />
      <AuthPanel trace={trace} />
      <RiskPanel trace={trace} />
      <DecisionPanel trace={trace} />
      <PiiPanel trace={trace} />
    </div>
  )
}
