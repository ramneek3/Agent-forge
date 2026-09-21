import { useEffect, useState } from 'react'
import { api } from '../api'

export function DocumentsPage() {
  const [docs, setDocs] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState('')

  const load = () => api.documents().then(setDocs).catch((e) => setError(String(e.message || e)))
  useEffect(() => {
    load()
  }, [])

  async function onUpload(file: File | null) {
    if (!file) return
    await api.uploadDocument(file)
    await load()
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-slate-500 mt-1">Ingest PDFs/text into the RAG knowledge base.</p>
      </header>
      <div className="panel rounded-xl p-4">
        <input
          type="file"
          accept=".pdf,.txt,.md"
          onChange={(e) => onUpload(e.target.files?.[0] || null)}
        />
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
      <div className="panel rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">Filename</th>
              <th className="px-4 py-3">Pages</th>
              <th className="px-4 py-3">Chunks</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={String(d.id)} className="border-t">
                <td className="px-4 py-3">{String(d.filename)}</td>
                <td className="px-4 py-3">{String(d.page_count)}</td>
                <td className="px-4 py-3">{String(d.chunk_count)}</td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(String(d.created_at)).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  <button
                    className="text-red-600 text-xs"
                    onClick={async () => {
                      await api.deleteDocument(String(d.id))
                      await load()
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ToolsPage() {
  const [tools, setTools] = useState<Array<Record<string, unknown>>>([])
  useEffect(() => {
    api.tools().then(setTools)
  }, [])
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Tools</h1>
        <p className="text-slate-500 mt-1">Registered tools available to agents.</p>
      </header>
      <div className="grid md:grid-cols-2 gap-3">
        {tools.map((t) => (
          <div key={String(t.name)} className="panel rounded-xl p-4">
            <div className="font-medium mono">{String(t.name)}</div>
            <div className="text-sm text-slate-600 mt-1">{String(t.description)}</div>
            <pre className="text-[11px] mt-3 bg-slate-50 p-2 rounded overflow-auto mono">
              {JSON.stringify(t.input_schema, null, 2)}
            </pre>
          </div>
        ))}
      </div>
    </div>
  )
}

export function MCPPage() {
  const [servers, setServers] = useState<Array<Record<string, unknown>>>([])
  const load = () => api.mcpServers().then(setServers)
  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">MCP Servers</h1>
        <p className="text-slate-500 mt-1">
          Model Context Protocol servers — discovery, connection, and tool enablement.
        </p>
      </header>
      {servers.map((s) => {
        const tools = (s.tools as Array<{ name: string; description: string }>) || []
        const enabled = new Set((s.enabled_tools as string[]) || [])
        return (
          <div key={String(s.id)} className="panel rounded-xl p-4 space-y-3">
            <div className="flex justify-between items-center">
              <div>
                <div className="font-medium text-lg">{String(s.name)}</div>
                <div className="text-xs mono text-slate-500">
                  {String(s.transport)} · {String(s.endpoint)} · {String(s.status)}
                </div>
              </div>
            </div>
            <div className="space-y-2">
              {tools.map((t) => (
                <label key={t.name} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={enabled.has(t.name)}
                    onChange={async (e) => {
                      const next = new Set(enabled)
                      if (e.target.checked) next.add(t.name)
                      else next.delete(t.name)
                      await api.enableMcpTools(String(s.id), [...next])
                      await load()
                    }}
                  />
                  <span>
                    <span className="mono font-medium">{t.name}</span>
                    <span className="block text-slate-500 text-xs">{t.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function ModelsPage() {
  const [models, setModels] = useState<Array<Record<string, unknown>>>([])
  useEffect(() => {
    api.models().then(setModels)
  }, [])
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Models</h1>
        <p className="text-slate-500 mt-1">
          Configured pricing and latency metadata used by the model router.
        </p>
      </header>
      <div className="panel rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Input $/1M</th>
              <th className="px-4 py-3">Output $/1M</th>
              <th className="px-4 py-3">Est. latency</th>
              <th className="px-4 py-3">Tier</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={String(m.key)} className="border-t">
                <td className="px-4 py-3">{String(m.provider)}</td>
                <td className="px-4 py-3 mono">{String(m.model)}</td>
                <td className="px-4 py-3">{String(m.input_per_1m_usd)}</td>
                <td className="px-4 py-3">{String(m.output_per_1m_usd)}</td>
                <td className="px-4 py-3">{String(m.estimated_latency_ms)} ms</td>
                <td className="px-4 py-3">{String(m.tier)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function TracesPage() {
  const [traces, setTraces] = useState<Array<Record<string, unknown>>>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    api.traces().then(setTraces)
  }, [])

  useEffect(() => {
    if (selected) api.trace(selected).then(setDetail)
  }, [selected])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Traces</h1>
        <p className="text-slate-500 mt-1">Inspect agent execution spans.</p>
      </header>
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="panel rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">Trace</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Latency</th>
                <th className="px-4 py-3">Tokens</th>
                <th className="px-4 py-3">Cost</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr
                  key={String(t.id)}
                  className="border-t cursor-pointer hover:bg-slate-50"
                  onClick={() => setSelected(String(t.id))}
                >
                  <td className="px-4 py-3 mono text-xs">{String(t.id).slice(0, 8)}</td>
                  <td className="px-4 py-3">{String(t.status)}</td>
                  <td className="px-4 py-3">{Number(t.latency_ms).toFixed(0)} ms</td>
                  <td className="px-4 py-3">{String(t.total_tokens)}</td>
                  <td className="px-4 py-3">${Number(t.estimated_cost_usd).toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel rounded-xl p-4">
          <div className="font-medium mb-3">Spans</div>
          {!detail && <div className="text-sm text-slate-500">Select a trace</div>}
          <ol className="space-y-3">
            {((detail?.spans as Array<Record<string, unknown>>) || []).map((s) => (
              <li key={String(s.id)} className="text-sm border-l-2 border-forge-400 pl-3">
                <div className="font-medium">{String(s.name)}</div>
                <div className="text-xs text-slate-500 mono">
                  {String(s.span_type)} · {Number(s.latency_ms).toFixed(1)} ms ·{' '}
                  {s.success ? 'ok' : 'fail'}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}

export function EvaluationsPage() {
  const [evals, setEvals] = useState<Array<Record<string, unknown>>>([])
  const [agents, setAgents] = useState<Array<{ id: string; name: string }>>([])
  const [agentId, setAgentId] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.evaluations().then(setEvals)
  useEffect(() => {
    load()
    api.agents().then((a) => {
      setAgents(a)
      if (a[0]) setAgentId(a[0].id)
    })
  }, [])

  async function run() {
    if (!agentId) return
    setBusy(true)
    try {
      await api.runEvaluation({
        agent_id: agentId,
        name: `eval-${new Date().toISOString().slice(0, 16)}`,
        dataset: [
          {
            question: 'What is AgentForge?',
            expected_answer: 'AgentForge is a production AI agent platform',
            expected_source: null,
          },
          {
            question: 'Please calculate 2 + 2',
            expected_answer: '4',
            expected_source: null,
          },
        ],
      })
      await load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-semibold">Evaluations</h1>
          <p className="text-slate-500 mt-1">
            Correctness, faithfulness, retrieval relevance, latency, and estimated cost.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            className="border rounded-md px-3 py-2 text-sm"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <button
            onClick={run}
            disabled={busy || !agentId}
            className="bg-forge-600 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50"
          >
            Run evaluation
          </button>
        </div>
      </header>
      <div className="space-y-3">
        {evals.map((e) => (
          <div key={String(e.id)} className="panel rounded-xl p-4">
            <div className="flex justify-between">
              <div className="font-medium">{String(e.name)}</div>
              <div className="text-xs bg-slate-100 px-2 py-0.5 rounded">{String(e.status)}</div>
            </div>
            <pre className="text-xs mt-3 bg-slate-50 p-3 rounded overflow-auto mono">
              {JSON.stringify(e.metrics, null, 2)}
            </pre>
          </div>
        ))}
      </div>
    </div>
  )
}

export function MonitoringPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Monitoring</h1>
        <p className="text-slate-500 mt-1">
          Prometheus scrapes <code className="mono text-xs">/metrics</code>. Grafana dashboards
          ship under <code className="mono text-xs">infra/grafana</code>.
        </p>
      </header>
      <div className="panel rounded-xl p-6 space-y-3 text-sm">
        <div>
          <div className="font-medium">Prometheus</div>
          <div className="text-slate-500">http://localhost:9090</div>
        </div>
        <div>
          <div className="font-medium">Grafana</div>
          <div className="text-slate-500">http://localhost:3001 (admin / agentforge)</div>
        </div>
        <div>
          <div className="font-medium">Key metrics</div>
          <ul className="list-disc ml-5 text-slate-600 mt-1 mono text-xs space-y-1">
            <li>agent_requests_total</li>
            <li>agent_request_latency_seconds</li>
            <li>llm_tokens_total / llm_cost_total</li>
            <li>tool_calls_total / rag_latency_seconds</li>
            <li>guardrail_failures_total</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
