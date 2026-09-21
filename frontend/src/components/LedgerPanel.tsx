import { useEffect, useState } from 'react'
import { api, type VerifyResult } from '../api'

// Beats 9 and 10 are performed entirely from this component.

export default function LedgerPanel() {
  const [result, setResult] = useState<VerifyResult | null>(null)
  const [records, setRecords] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try { setRecords((await api.ledgerRecords(40)).records) } catch (e: any) { setError(String(e)) }
  }
  useEffect(() => { load() }, [])

  const verify = async () => {
    setBusy(true); setError(null)
    try { setResult(await api.verifyLedger()); await load() }
    catch (e: any) { setError(String(e)) }
    finally { setBusy(false) }
  }

  const exportLedger = async () => {
    try {
      const data = await api.exportLedger()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob); a.download = 'ledger-export.json'; a.click()
    } catch (e: any) { setError(String(e)) }
  }

  const exportAsCustomer = async () => {
    setError(null)
    try {
      await api.exportLedger('customer')
      setError('A customer token was accepted. That is a bug and the RBAC test should have caught it.')
    } catch (e: any) {
      setError('Correctly refused for a customer token: ' + String(e).slice(0, 160))
    }
  }

  return (
    <div className="panel">
      <h2>Tamper-evident ledger</h2>
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={verify} disabled={busy}>{busy ? 'Verifying...' : 'Verify Ledger'}</button>
        <button className="secondary" onClick={exportLedger}>Export for compliance</button>
        <button className="secondary" onClick={exportAsCustomer}>Try export as customer</button>
      </div>

      {result && (result.ok ? (
        <div className="verify-ok">
          Chain verified. {result.records_checked} records checked out of {result.total_records ?? '?'} in{' '}
          {result.elapsed_ms} ms using the {result.method} method ({result.probes} probes).
        </div>
      ) : (
        <div className="verify-bad">
          <div style={{ fontSize: 18 }}>CHAIN BROKEN</div>
          <div>First break at record index <strong>{result.first_broken_index}</strong></div>
          <div>Record id <span className="mono">{result.broken_record_id}</span></div>
          <div>Failed check: <strong>{result.broken_check}</strong></div>
          <div className="hash" style={{ marginTop: 6 }}>expected {result.expected_hash}</div>
          <div className="hash">actual&nbsp;&nbsp; {result.actual_hash}</div>
          <div style={{ marginTop: 6, fontWeight: 400 }}>
            Located in {result.elapsed_ms} ms by checking {result.records_checked} records
            across {result.probes} checkpoint probes.
          </div>
        </div>
      ))}
      {error && <p style={{ color: 'var(--red)' }}>{error}</p>}

      <h3>Chain, most recent first</h3>
      <table>
        <thead><tr><th>#</th><th>kind</th><th>time</th><th>hash</th><th>links to</th></tr></thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.idx} className={result && !result.ok && r.idx === result.first_broken_index ? 'broken' : ''}>
              <td className="mono">{r.idx}</td>
              <td>{r.kind}</td>
              <td className="mono">{String(r.ts).slice(11, 19)}</td>
              <td className="hash">{String(r.hash).slice(0, 24)}...</td>
              <td className="hash">{String(r.prev_hash).slice(0, 16)}...</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        H(i) = SHA-256( H(i-1) || canonical_json(M_i) || t_i ), signed with HMAC-SHA-256 under a
        key that is not stored in the database. A checkpoint is written every 64 records.
        To break it live: <span className="mono">python scripts/tamper_demo.py</span>, then click
        Verify Ledger again.
      </p>
    </div>
  )
}
