import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, type DashboardStats } from '../api'

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel rounded-xl p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(String(e.message || e)))
  }, [])

  const chartData = [
    { name: 'Requests', value: stats?.requests_today ?? 0 },
    { name: 'Tokens/100', value: Math.round((stats?.tokens_used ?? 0) / 100) },
    { name: 'Errors %', value: Math.round((stats?.error_rate ?? 0) * 100) },
    { name: 'Latency', value: Math.round(stats?.average_latency_ms ?? 0) },
  ]

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Operations Dashboard</h1>
        <p className="text-slate-500 mt-1">
          Live view of agents, traffic, tokens, and estimated cost.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Backend unreachable: {error}. Start the API on port 8000.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Active agents" value={String(stats?.active_agents ?? '—')} />
        <Stat label="Production agents" value={String(stats?.production_agents ?? '—')} />
        <Stat label="Requests today" value={String(stats?.requests_today ?? '—')} />
        <Stat
          label="Avg latency"
          value={stats ? `${stats.average_latency_ms.toFixed(0)} ms` : '—'}
        />
        <Stat label="Tokens used" value={stats ? String(stats.tokens_used) : '—'} />
        <Stat
          label="Est. cost"
          value={stats ? `$${stats.estimated_cost_usd.toFixed(6)}` : '—'}
          hint="Estimates from configured pricing"
        />
        <Stat
          label="Error rate"
          value={stats ? `${(stats.error_rate * 100).toFixed(1)}%` : '—'}
        />
        <Stat
          label="Latest evals"
          value={String(stats?.latest_evaluations?.length ?? 0)}
        />
      </div>

      <div className="panel rounded-xl p-4 h-72">
        <div className="text-sm font-medium mb-3">Today at a glance</div>
        <ResponsiveContainer width="100%" height="90%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="value" fill="#0284c7" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="panel rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium">Latest evaluations</div>
          <Link to="/evaluations" className="text-sm text-forge-600 hover:underline">
            View all
          </Link>
        </div>
        <div className="space-y-2">
          {(stats?.latest_evaluations || []).length === 0 && (
            <div className="text-sm text-slate-500">No evaluations yet.</div>
          )}
          {(stats?.latest_evaluations || []).map((e) => (
            <div
              key={String(e.id)}
              className="flex items-center justify-between text-sm border-b border-slate-100 py-2"
            >
              <span className="font-medium">{String(e.name)}</span>
              <span className="mono text-slate-500">{String(e.status)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
