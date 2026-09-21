import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Agent } from '../api'

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = () => api.agents().then(setAgents).catch((e) => setError(String(e.message || e)))
  useEffect(() => {
    load()
  }, [])

  async function create() {
    if (!name.trim()) return
    setBusy(true)
    setError('')
    try {
      await api.createAgent({
        name: name.trim(),
        description: 'Created from dashboard',
        system_prompt:
          'You are a production AgentForge agent. Use tools and knowledge when needed. Cite sources.',
        model_provider: 'mock',
        model: 'mock-smart',
        routing_strategy: 'MANUAL',
        tools: ['calculator', 'weather', 'web_search', 'database_query'],
        mcp_config: { enabled: true, server_name: 'github' },
        rag_config: { enabled: true, top_k: 5, similarity_threshold: 0.2 },
      })
      setName('')
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function deploy(agent: Agent) {
    const v = agent.current_version
    if (!v) return
    setBusy(true)
    try {
      if (v.status === 'draft') {
        await api.promote(agent.id, v.id, 'staging')
        await api.promote(agent.id, v.id, 'production')
      } else if (v.status === 'staging') {
        await api.promote(agent.id, v.id, 'production')
      }
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function rollback(agent: Agent) {
    const versions = await api.versions(agent.id)
    const archived = versions.find((v) => v.status === 'archived' || v.version_number < (agent.current_version?.version_number || 0))
    if (!archived) {
      setError('No prior version to roll back to')
      return
    }
    await api.rollback(agent.id, archived.id)
    await load()
  }

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Agents</h1>
          <p className="text-slate-500 mt-1">Create, deploy, and roll back agent versions.</p>
        </div>
      </header>

      <div className="panel rounded-xl p-4 flex gap-2 items-center">
        <input
          className="flex-1 border border-slate-200 rounded-md px-3 py-2 text-sm"
          placeholder="New agent name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          onClick={create}
          disabled={busy}
          className="bg-forge-600 text-white text-sm px-4 py-2 rounded-md hover:bg-forge-700 disabled:opacity-50"
        >
          Create
        </button>
      </div>

      {error && <div className="text-sm text-red-600">{error}</div>}

      <div className="panel rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Agent</th>
              <th className="px-4 py-3 font-medium">Version</th>
              <th className="px-4 py-3 font-medium">Model</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Requests</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id} className="border-t border-slate-100">
                <td className="px-4 py-3">
                  <Link className="text-forge-700 font-medium hover:underline" to={`/agents/${a.id}`}>
                    {a.name}
                  </Link>
                </td>
                <td className="px-4 py-3 mono">v{a.current_version?.version_number ?? '—'}</td>
                <td className="px-4 py-3 mono text-xs">
                  {a.current_version?.model_provider}/{a.current_version?.model}
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex px-2 py-0.5 rounded bg-slate-100 text-xs">
                    {a.current_version?.status ?? '—'}
                  </span>
                </td>
                <td className="px-4 py-3">{a.request_count}</td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(a.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 space-x-2">
                  <Link to={`/playground?agent=${a.id}`} className="text-forge-600 hover:underline">
                    Chat
                  </Link>
                  <button onClick={() => deploy(a)} className="text-ember-500 hover:underline">
                    Deploy
                  </button>
                  <button onClick={() => rollback(a)} className="text-slate-600 hover:underline">
                    Rollback
                  </button>
                </td>
              </tr>
            ))}
            {agents.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  No agents yet. Create one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
