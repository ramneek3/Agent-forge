import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Agent, type AgentVersion } from '../api'

export function AgentDetailsPage() {
  const { id } = useParams()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [versions, setVersions] = useState<AgentVersion[]>([])
  const [model, setModel] = useState('mock-smart')
  const [provider, setProvider] = useState('mock')
  const [strategy, setStrategy] = useState('MANUAL')
  const [prompt, setPrompt] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => {
    if (!id) return
    const [a, v] = await Promise.all([api.agent(id), api.versions(id)])
    setAgent(a)
    setVersions(v)
    if (a.current_version) {
      setModel(a.current_version.model)
      setProvider(a.current_version.model_provider)
      setStrategy(a.current_version.routing_strategy)
      setPrompt(a.current_version.system_prompt)
    }
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e.message || e)))
  }, [id])

  async function saveVersion() {
    if (!id) return
    await api.createVersion(id, {
      model,
      model_provider: provider,
      routing_strategy: strategy,
      system_prompt: prompt,
      fallback_provider: 'mock',
      fallback_model: 'mock-fast',
    })
    setMsg('New draft version created')
    await load()
  }

  return (
    <div className="space-y-6">
      <header>
        <Link to="/agents" className="text-sm text-forge-600 hover:underline">
          ← Agents
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{agent?.name ?? 'Agent'}</h1>
        <p className="text-slate-500">{agent?.description}</p>
      </header>

      {msg && <div className="text-sm text-slate-600">{msg}</div>}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="panel rounded-xl p-4 space-y-3">
          <div className="font-medium">Edit configuration (new version)</div>
          <label className="block text-xs text-slate-500">Provider</label>
          <select
            className="w-full border rounded-md px-3 py-2 text-sm"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="mock">mock</option>
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
            <option value="google">google</option>
            <option value="openrouter">openrouter</option>
          </select>
          <label className="block text-xs text-slate-500">Model</label>
          <input
            className="w-full border rounded-md px-3 py-2 text-sm mono"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <label className="block text-xs text-slate-500">Routing strategy</label>
          <select
            className="w-full border rounded-md px-3 py-2 text-sm"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
          >
            <option value="MANUAL">MANUAL</option>
            <option value="CHEAPEST">CHEAPEST</option>
            <option value="FASTEST">FASTEST</option>
            <option value="FALLBACK">FALLBACK</option>
          </select>
          <label className="block text-xs text-slate-500">System prompt</label>
          <textarea
            className="w-full border rounded-md px-3 py-2 text-sm h-32"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <button
            onClick={saveVersion}
            className="bg-forge-600 text-white text-sm px-4 py-2 rounded-md"
          >
            Create version
          </button>
        </div>

        <div className="panel rounded-xl p-4">
          <div className="font-medium mb-3">Version history</div>
          <div className="space-y-2 max-h-96 overflow-auto">
            {versions.map((v) => (
              <div key={v.id} className="border border-slate-100 rounded-lg p-3 text-sm">
                <div className="flex justify-between">
                  <span className="font-medium mono">v{v.version_number}</span>
                  <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">{v.status}</span>
                </div>
                <div className="text-xs text-slate-500 mt-1 mono">
                  {v.model_provider}/{v.model} · {v.routing_strategy}
                </div>
                <div className="mt-2 space-x-2">
                  {v.status === 'draft' && (
                    <button
                      className="text-forge-600 text-xs"
                      onClick={async () => {
                        await api.promote(id!, v.id, 'staging')
                        await load()
                      }}
                    >
                      → staging
                    </button>
                  )}
                  {v.status === 'staging' && (
                    <button
                      className="text-ember-500 text-xs"
                      onClick={async () => {
                        await api.promote(id!, v.id, 'production')
                        await load()
                      }}
                    >
                      → production
                    </button>
                  )}
                  {v.status !== 'production' && (
                    <button
                      className="text-slate-600 text-xs"
                      onClick={async () => {
                        await api.rollback(id!, v.id)
                        await load()
                      }}
                    >
                      rollback to this
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
