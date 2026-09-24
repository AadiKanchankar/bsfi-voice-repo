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

export type Customer = {
  customer_id: string; name: string; language: string
  enrolled: boolean; source: string | null
  accounts: number; holdings: number; is_presenter: boolean
}

export type CallRow = {
  call_id: string; customer_id: string | null; customer_name: string | null
  started_at: string; ended_at: string | null; language: string | null
  channel: string; final_state: string | null; recording_consent: number
  turns: number; max_tier: number | null; recordings: number; cases: number
  interrupted: number
}

export type RecordingRow = {
  recording_id: string; turn_id: number | null; speaker: string
  duration_s: number | null; language: string | null; sha256: string
  created_at: string; retention_until: string; purged_at: string | null
}

export type LedgerRow = {
  idx: number; record_id: string; kind: string; ts: string; hash: string
  payload: any; verified: boolean; reason: string | null
}

export type CallDetail = {
  call: CallRow & { consent_ref: string | null; notice_completed: number }
  customer: any | null
  sessions: any[]; turns: any[]; traces: Trace[]
  recordings: RecordingRow[]; cases: any[]; ledger: LedgerRow[]
}

export type CallFilters = {
  customer_id?: string; call_id?: string; date_from?: string; date_to?: string
  decision?: string; tier?: number | string; language?: string
}

const OFFICER = 'compliance_officer'

export const api = {
  customers: () => req('/customers') as Promise<{ customers: Customer[]; presenter_id: string }>,
  register: (body: { name: string; mobile?: string; language?: string }) =>
    req('/customers', { method: 'POST', body: JSON.stringify(body) }) as
      Promise<{ customer_id: string; name: string; mobile_masked: string | null }>,
  identify: (sessionId: string, identifier: string) =>
    req(`/session/${sessionId}/identify`, { method: 'POST', body: JSON.stringify({ identifier }) }) as
      Promise<{ identified: boolean; customer_id?: string; name?: string; enrolled?: boolean; next?: string; reason?: string }>,
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

  // R6. The agent console.
  agentQueue: (status = 'open') =>
    req(`/agent/queue?status=${status}`, {}, 'agent') as Promise<{ cases: any[] }>,
  acceptCase: (caseId: string, agentId: string) =>
    req(`/agent/cases/${caseId}/accept?agent_id=${agentId}`, { method: 'POST' }, 'agent'),
  agentReply: (caseId: string, agentId: string, text: string, language = 'en') =>
    req(`/agent/cases/${caseId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, text, language }),
    }, 'agent'),
  closeCase: (caseId: string, agentId: string, outcome: string) =>
    req(`/agent/cases/${caseId}/close`, {
      method: 'POST', body: JSON.stringify({ agent_id: agentId, outcome }),
    }, 'agent'),
  intakeQuestions: (caseId: string) =>
    req(`/cases/${caseId}/intake`) as Promise<{ questions: any[]; reason: string }>,
  sendIntake: (caseId: string, answers: Record<string, string>) =>
    req(`/cases/${caseId}/intake`, { method: 'POST', body: JSON.stringify({ answers }) }),
  protectiveActions: (reason: string) =>
    req(`/protective-actions?reason=${reason}`) as Promise<{ actions: any[] }>,
  doProtectiveAction: (body: {
    action: string; customer_id: string; confirmed: boolean
    case_id?: string; call_id?: string
  }) => req('/protective-action', { method: 'POST', body: JSON.stringify(body) }),

  // R5. Recording real evaluation audio. The current set is rendered with
  // Piper, which makes the Hindi, Marathi and code-mixed error rates invalid:
  // a synthesiser transcribing its own output measures the round trip.
  evalScript: (language: string) =>
    req(`/eval/script?language=${language}`, {}, 'compliance_officer') as
      Promise<{ language: string; count: number
                lines: { id: string; text: string; intent: string | null; recorded: boolean }[] }>,
  evalRecord: async (id: string, blob: Blob) => {
    const fd = new FormData()
    fd.append('audio', blob, `${id}.webm`)
    const token = await getToken('customer')
    const res = await fetch(`/api/eval/record/${id}`, {
      method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`)
    return res.json() as Promise<{ id: string; seconds: number }>
  },
  evalAudioUrl: async (id: string) => {
    const token = await getToken('compliance_officer')
    const res = await fetch(`/api/eval/audio/${id}`, {
      headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(`${res.status}`)
    return URL.createObjectURL(await res.blob())
  },
  providers: () => req('/providers', {}, 'compliance_officer') as
    Promise<{ tts: Record<string, any>; selected: Record<string, string>
              usage: Record<string, any> }>,

  // R3. The server owns the call state; the client reads it and asks for
  // transitions, it never decides one.
  callState: (callId: string) => req(`/call/${callId}/state`) as
    Promise<{ call_id: string; state: string; turn_id: number | null; turn_in_flight: boolean }>,
  interrupt: (callId: string, body: {
    played_ms?: number; played_chars?: number; reply_chars?: number; source?: string
  } = {}) => req(`/call/${callId}/interrupt`, { method: 'POST', body: JSON.stringify(body) }) as
    Promise<{ state: string; interrupted_from: string; fraction_delivered: number | null
              pending_dropped: string[] }>,
  endCall: (callId: string) => req(`/call/${callId}/end`, { method: 'POST' }) as
    Promise<{ state: string }>,

  // R2. The lookup. A miss is a 404 with a message, never an empty list.
  resolve: (q: string) =>
    req(`/search?q=${encodeURIComponent(q)}`, {}, OFFICER) as
      Promise<{ kind: 'call' | 'session' | 'customer' | 'case'; id: string; call_id?: string }>,
  calls: (f: CallFilters = {}) => {
    const qs = new URLSearchParams(
      Object.entries(f).filter(([, v]) => v !== '' && v != null) as [string, string][])
    return req(`/calls?${qs}`, {}, OFFICER) as Promise<{ calls: CallRow[]; count: number }>
  },
  call: (id: string) => req(`/calls/${id}`, {}, OFFICER) as Promise<CallDetail>,
  customer: (id: string) => req(`/customers/${id}`, {}, OFFICER) as
    Promise<{ customer: any; calls: CallRow[]; cases: any[] }>,
  cases: (status?: string) =>
    req(`/cases${status ? `?status=${status}` : ''}`, {}, OFFICER) as
      Promise<{ cases: any[]; count: number }>,
  accessLog: (limit = 50) => req(`/access-log?limit=${limit}`, {}, OFFICER) as
    Promise<{ entries: any[] }>,
  recordingUrl: async (id: string) => {
    // Fetched with the officer token and turned into an object URL, because
    // an <audio src> cannot carry an Authorization header.
    const token = await getToken(OFFICER)
    const res = await fetch(`/api/recordings/${id}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`)
    return URL.createObjectURL(await res.blob())
  },
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
  speak: async (text: string, language: string, fixed = false) => {
    const token = await getToken('customer')
    const res = await fetch(
      `/api/tts?text=${encodeURIComponent(text)}&language=${language}&fixed=${fixed}`,
      { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return null
    return res.blob()
  },
  // R4. Synthesis is 71% of the wait. A reply is about four phrases, so
  // speaking the first one while the rest is still being made is the single
  // largest win available, and it needs no streaming protocol.
  speakPlan: (text: string, language: string) =>
    req(`/tts/plan?text=${encodeURIComponent(text)}&language=${language}`) as
      Promise<{ phrases: string[]; language: string }>,
}
