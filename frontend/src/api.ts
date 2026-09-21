const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail?.message || err.message || err.detail || res.statusText)
  }
  return res.json()
}

export type AgentVersion = {
  id: string
  agent_id: string
  version_number: number
  status: string
  system_prompt: string
  model_provider: string
  model: string
  temperature: number
  routing_strategy: string
  fallback_provider?: string
  fallback_model?: string
  tools: string[]
  mcp_config: Record<string, unknown>
  rag_config: Record<string, unknown>
  guardrail_config: Record<string, unknown>
  created_at: string
}

export type Agent = {
  id: string
  name: string
  description: string
  created_at: string
  production_version_id?: string
  request_count: number
  current_version?: AgentVersion
}

export type ChatResponse = {
  answer: string
  agent_id: string
  agent_version: number
  agent_version_id: string
  model: string
  provider: string
  trace_id: string
  token_usage: { input_tokens: number; output_tokens: number; total_tokens: number }
  estimated_cost: {
    estimated_input_cost_usd: number
    estimated_output_cost_usd: number
    estimated_total_cost_usd: number
  }
  latency_ms: number
  citations: Array<{
    document_id: string
    filename: string
    page_number?: number
    score?: number
    snippet?: string
  }>
  conversation_id: string
  fallback_used: boolean
  tool_results: Array<Record<string, unknown>>
  mcp_results: Array<Record<string, unknown>>
  guardrail_results: Array<Record<string, unknown>>
}

export type Trace = {
  id: string
  agent_id: string
  agent_version_id: string
  status: string
  latency_ms: number
  total_tokens: number
  estimated_cost_usd: number
  error?: string
  created_at: string
  spans: Array<{
    id: string
    span_type: string
    name: string
    latency_ms: number
    success: boolean
    metadata_json: Record<string, unknown>
    start_time: string
  }>
}

export type DashboardStats = {
  active_agents: number
  production_agents: number
  requests_today: number
  average_latency_ms: number
  tokens_used: number
  estimated_cost_usd: number
  error_rate: number
  latest_evaluations: Array<Record<string, unknown>>
}

export const api = {
  stats: () => request<DashboardStats>('/dashboard/stats'),
  agents: () => request<Agent[]>('/agents'),
  agent: (id: string) => request<Agent>(`/agents/${id}`),
  createAgent: (body: Record<string, unknown>) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(body) }),
  versions: (id: string) => request<AgentVersion[]>(`/agents/${id}/versions`),
  createVersion: (id: string, body: Record<string, unknown>) =>
    request<AgentVersion>(`/agents/${id}/versions`, { method: 'POST', body: JSON.stringify(body) }),
  promote: (agentId: string, versionId: string, target_status: string) =>
    request<AgentVersion>(`/agents/${agentId}/versions/${versionId}/promote`, {
      method: 'POST',
      body: JSON.stringify({ target_status }),
    }),
  rollback: (agentId: string, version_id: string) =>
    request<AgentVersion>(`/agents/${agentId}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ version_id }),
    }),
  chat: (agentId: string, body: Record<string, unknown>) =>
    request<ChatResponse>(`/agents/${agentId}/chat`, { method: 'POST', body: JSON.stringify(body) }),
  documents: () => request<Array<Record<string, unknown>>>('/documents'),
  uploadDocument: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Record<string, unknown>>('/documents', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) => request(`/documents/${id}`, { method: 'DELETE' }),
  tools: () => request<Array<Record<string, unknown>>>('/tools'),
  mcpServers: () => request<Array<Record<string, unknown>>>('/mcp/servers'),
  enableMcpTools: (serverId: string, enabled_tools: string[]) =>
    request(`/mcp/servers/${serverId}/tools`, {
      method: 'POST',
      body: JSON.stringify({ enabled_tools }),
    }),
  models: () => request<Array<Record<string, unknown>>>('/models'),
  traces: () => request<Trace[]>('/traces'),
  trace: (id: string) => request<Trace>(`/traces/${id}`),
  evaluations: () => request<Array<Record<string, unknown>>>('/evaluations'),
  runEvaluation: (body: Record<string, unknown>) =>
    request('/evaluations/run', { method: 'POST', body: JSON.stringify(body) }),
}
