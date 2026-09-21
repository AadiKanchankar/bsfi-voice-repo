import { useEffect, useState } from 'react'
import { api, type Capability } from '../api'

// The honesty registry, rendered. A panel member who asks "is that real?"
// gets the answer off the screen.
export default function CapabilityLegend() {
  const [caps, setCaps] = useState<Record<string, Capability>>({})
  const [legend, setLegend] = useState<Record<string, string>>({})
  useEffect(() => {
    api.capabilities().then((d) => { setCaps(d.capabilities); setLegend(d.legend) }).catch(() => {})
  }, [])
  return (
    <div className="panel">
      <h2>Capability registry</h2>
      <table>
        <thead><tr><th>component</th><th>status</th><th>implementation</th></tr></thead>
        <tbody>
          {Object.entries(caps).map(([name, c]) => (
            <tr key={name}>
              <td className="mono">{name}</td>
              <td><span className={'tag ' + c.status}>{c.status}</span></td>
              <td>{c.implementation}{c.note && <div className="muted">{c.note}</div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        {Object.entries(legend).map(([k, v]) => <span key={k}><strong>{k}</strong>: {v}. </span>)}
      </p>
    </div>
  )
}
