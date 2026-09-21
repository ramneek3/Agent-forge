import { NavLink, Outlet } from 'react-router-dom'
import {
  Activity,
  Bot,
  Boxes,
  FileText,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  MessageSquare,
  Network,
  Plug,
  ScrollText,
} from 'lucide-react'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/playground', label: 'Playground', icon: MessageSquare },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/tools', label: 'Tools', icon: Boxes },
  { to: '/mcp', label: 'MCP Servers', icon: Plug },
  { to: '/models', label: 'Models', icon: Network },
  { to: '/traces', label: 'Traces', icon: ScrollText },
  { to: '/evaluations', label: 'Evaluations', icon: FlaskConical },
  { to: '/monitoring', label: 'Monitoring', icon: Gauge },
]

export function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 border-r border-slate-200/80 bg-ink-950 text-slate-100 flex flex-col">
        <div className="px-5 py-6 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Activity className="text-forge-400" size={22} />
            <div>
              <div className="font-display font-bold tracking-tight text-lg">AgentForge</div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                Agent Platform
              </div>
            </div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition ${
                  isActive
                    ? 'bg-forge-600/30 text-white'
                    : 'text-slate-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 text-[11px] text-slate-500 border-t border-white/10 mono">
          v1.0 · local ops
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
