// One place for the API surface, so the two routes cannot drift apart.

export type Capability = { status: 'REAL' | 'BASELINE' | 'SIMULATED'; implementation: string; note?: string }

export type StageRecord = {
  stage: string; started_at: string; duration_ms: number; inputs_digest: string
  outputs: any; confidence: number | null; model_id: string | null
  capability: 'REAL' | 'BASELINE' | 'SIMULATED'; notes: string | null
}

export type LanguageSpan = { lang: string; start_word: number; end_word: number; text: string; confidence: number }
export type RetrievedPassage = { doc_id: string; version: string; section: string; effective_date: string; score: number; text: string }
export type AuthOutcome = {
  method: string; speaker_score: number | null; spoof_score: number | null
  s_verify: number | null; threshold: number | null; passed: boolean
  otp_required: boolean; otp_passed: boolean | null
  readback_text: string | null; readback_confirmed: boolean | null; reason: string | null
}

export type Trace = {
  trace_id: string; session_id: string; turn_index: number; consent_ref: string; created_at: string
  stages: StageRecord[]; transcript: string | null
  language_spans: LanguageSpan[]; code_mix_index: number | null; dominant_language: string | null
  intent: string | null; intent_confidence: number | null; slots: Record<string, any>
  retrieved: RetrievedPassage[]; retrieval_max_score: number | null; retrieval_floor: number | null
  asr_confidence: number | null; fused_confidence: number | null; fusion_weights: Record<string, number>
  risk_score: number | null; risk_tier: number | null; risk_components: any
  tier_overridden: boolean; tier_ratcheted: boolean; tau_required: number | null
  auth: AuthOutcome | null
  decision: 'automated' | 'refused' | 'escalated' | null; decision_reason: string | null
  action_taken: string | null; action_result: any; reply_text: string | null; reply_language: string | null
  pii_tokens: Record<string, string>; redacted: boolean; handover_packet_ref: string | null
}

export type VerifyResult = {
  ok: boolean; records_checked: number; total_records?: number; method: string; probes: number
  first_broken_index: number | null; broken_record_id: string | null
  broken_check?: string; expected_hash: string | null; actual_hash: string | null
  elapsed_ms?: number; segment?: [number, number]; checkpoint_interval?: number
}

const TOKEN_KEY = 'bfsi_token_'

async function req(path: string, opts: RequestInit = {}, role = 'customer') {
  const token = await getToken(role)
  const res = await fetch('/api' + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(opts.headers || {}) },
  })
  if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 300)}`)
  return res.json()
}

export async function getToken(role: string): Promise<string> {
  const cached = sessionStorage.getItem(TOKEN_KEY + role)
  if (cached) return cached
  const res = await fetch('/api/auth/demo-token', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subject: `demo-${role}`, role }),
  })
  const { token } = await res.json()
  sessionStorage.setItem(TOKEN_KEY + role, token)
  return token
}

export const api = {
  capabilities: () => fetch('/api/capabilities').then((r) => r.json()),
  startSession: (body: any) => req('/session/consent', { method: 'POST', body: JSON.stringify(body) }),
  textTurn: (body: any) => req('/turn/text', { method: 'POST', body: JSON.stringify(body) }) as Promise<Trace>,
  sessionTraces: (id: string, role = 'compliance_officer') =>
    req(`/session/${id}/traces`, {}, role) as Promise<{ traces: Trace[] }>,
  verifyLedger: () => req('/ledger/verify', { method: 'POST' }, 'compliance_officer') as Promise<VerifyResult>,
  ledgerRecords: (limit = 40) => req(`/ledger/records?limit=${limit}`, {}, 'compliance_officer'),
  exportLedger: (role = 'compliance_officer') => req('/ledger/export', {}, role),
  handovers: () => req('/handovers', {}, 'agent'),
  claimHandover: (traceId: string) => req(`/agent/handover/${traceId}`, { method: 'POST' }, 'agent'),
  metrics: () => req('/metrics', {}, 'compliance_officer'),
  kb: () => req('/kb', {}, 'compliance_officer'),
  withdraw: (id: string) => req(`/session/${id}/withdraw`, { method: 'POST' }),
  audioTurn: async (sessionId: string, blob: Blob) => {
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('audio', blob, 'turn.wav')
    const token = await getToken('customer')
    const res = await fetch('/api/turn/audio', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<Trace>
  },
  enroll: async (customerId: string, clips: Blob[]) => {
    const fd = new FormData()
    fd.append('customer_id', customerId)
    clips.forEach((c, i) => fd.append('clips', c, `clip${i}.webm`))
    const token = await getToken('customer')
    const res = await fetch('/api/enroll', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  verifyVoice: async (sessionId: string, blob: Blob) => {
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('audio', blob, 'verify.webm')
    const token = await getToken('customer')
    const res = await fetch('/api/verify', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  verifyDemo: async (sessionId: string) => {
    const fd = new FormData()
    fd.append('session_id', sessionId)
    const token = await getToken('customer')
    const res = await fetch('/api/verify/demo', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  speak: async (text: string, language: string) => {
    const token = await getToken('customer')
    const res = await fetch(`/api/tts?text=${encodeURIComponent(text)}&language=${language}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return null
    return res.blob()
  },
}
