import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type Agent, type ChatResponse, type Trace } from '../api'

type Msg = { role: 'user' | 'assistant'; content: string; meta?: ChatResponse }

export function PlaygroundPage() {
  const [params] = useSearchParams()
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentId, setAgentId] = useState(params.get('agent') || '')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [last, setLast] = useState<ChatResponse | null>(null)
  const [trace, setTrace] = useState<Trace | null>(null)
  const [forceFail, setForceFail] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.agents().then((list) => {
      setAgents(list)
      if (!agentId && list[0]) setAgentId(list[0].id)
    })
  }, [])

  const selected = useMemo(() => agents.find((a) => a.id === agentId), [agents, agentId])

  async function send() {
    if (!agentId || !input.trim()) return
    setBusy(true)
    setError('')
    const userMsg = input.trim()
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: userMsg }])
    try {
      const resp = await api.chat(agentId, {
        message: userMsg,
        conversation_id: conversationId,
        force_primary_failure: forceFail,
      })
      setConversationId(resp.conversation_id)
      setLast(resp)
      setMessages((m) => [...m, { role: 'assistant', content: resp.answer, meta: resp }])
      const t = await api.trace(resp.trace_id)
      setTrace(t)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Agent Playground</h1>
          <p className="text-slate-500 mt-1">
            Chat on the left · execution trace on the right
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            className="border rounded-md px-3 py-2 text-sm min-w-48"
            value={agentId}
            onChange={(e) => {
              setAgentId(e.target.value)
              setMessages([])
              setConversationId(undefined)
              setTrace(null)
              setLast(null)
            }}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <label className="text-xs flex items-center gap-1.5 text-slate-600">
            <input type="checkbox" checked={forceFail} onChange={(e) => setForceFail(e.target.checked)} />
            Force primary failure (fallback demo)
          </label>
        </div>
      </header>

      {selected && (
        <div className="text-xs text-slate-500 mono">
          {selected.current_version?.model_provider}/{selected.current_version?.model} ·{' '}
          {selected.current_version?.routing_strategy} · status{' '}
          {selected.current_version?.status}
        </div>
      )}

      {error && <div className="text-sm text-red-600">{error}</div>}

      <div className="grid lg:grid-cols-2 gap-4 min-h-[560px]">
        <div className="panel rounded-xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 text-sm font-medium">Conversation</div>
          <div className="flex-1 overflow-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-sm text-slate-500">
                Try: “Based on the knowledge base, what is AgentForge?” or “Please calculate 21 * 2”
                or “List GitHub issues for the repository”.
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 text-sm max-w-[90%] ${
                  m.role === 'user'
                    ? 'bg-forge-600 text-white ml-auto'
                    : 'bg-slate-100 text-slate-900'
                }`}
              >
                {m.content}
              </div>
            ))}
          </div>
          <div className="p-3 border-t border-slate-100 flex gap-2">
            <input
              className="flex-1 border rounded-md px-3 py-2 text-sm"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="Ask the agent…"
              disabled={busy || !agentId}
            />
            <button
              onClick={send}
              disabled={busy || !agentId}
              className="bg-forge-600 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>

        <div className="panel rounded-xl overflow-auto">
          <div className="px-4 py-3 border-b border-slate-100 text-sm font-medium">Execution trace</div>
          <div className="p-4 space-y-4">
            {last && (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Latency" value={`${last.latency_ms.toFixed(1)} ms`} />
                <Metric label="Model" value={`${last.provider}/${last.model}`} />
                <Metric label="Tokens" value={String(last.token_usage.total_tokens)} />
                <Metric
                  label="Est. cost"
                  value={`$${last.estimated_cost.estimated_total_cost_usd.toFixed(8)}`}
                />
                <Metric label="Fallback" value={last.fallback_used ? 'yes' : 'no'} />
                <Metric label="Trace ID" value={last.trace_id.slice(0, 8) + '…'} />
              </div>
            )}

            <ol className="relative border-l border-slate-200 ml-2 space-y-4">
              {(trace?.spans || []).map((s) => (
                <li key={s.id} className="ml-4">
                  <div
                    className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full ${
                      s.success ? 'bg-forge-500' : 'bg-red-500'
                    }`}
                  />
                  <div className="text-sm font-medium">{s.name}</div>
                  <div className="text-xs text-slate-500 mono">
                    {s.span_type} · {s.latency_ms.toFixed(1)} ms
                  </div>
                </li>
              ))}
              {!trace && (
                <div className="text-sm text-slate-500 ml-4">Send a message to see the trace.</div>
              )}
            </ol>

            {last?.citations && last.citations.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">Citations</div>
                <div className="space-y-2">
                  {last.citations.map((c, i) => (
                    <div key={i} className="text-xs border border-slate-100 rounded-md p-2">
                      <div className="font-medium">
                        {c.filename} {c.page_number != null ? `(p.${c.page_number})` : ''}
                      </div>
                      <div className="text-slate-500 mt-1">{c.snippet}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {last?.tool_results && last.tool_results.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">Tool calls</div>
                <pre className="text-xs bg-slate-50 rounded-md p-2 overflow-auto mono">
                  {JSON.stringify(last.tool_results, null, 2)}
                </pre>
              </div>
            )}

            {last?.mcp_results && last.mcp_results.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">MCP calls</div>
                <pre className="text-xs bg-slate-50 rounded-md p-2 overflow-auto mono">
                  {JSON.stringify(last.mcp_results, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded-md px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mono text-slate-800 truncate">{value}</div>
    </div>
  )
}
