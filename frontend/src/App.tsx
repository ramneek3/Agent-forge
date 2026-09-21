import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DashboardPage } from './pages/Dashboard'
import { AgentsPage } from './pages/Agents'
import { AgentDetailsPage } from './pages/AgentDetails'
import { PlaygroundPage } from './pages/Playground'
import {
  DocumentsPage,
  EvaluationsPage,
  MCPPage,
  ModelsPage,
  MonitoringPage,
  ToolsPage,
  TracesPage,
} from './pages/OtherPages'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/:id" element={<AgentDetailsPage />} />
          <Route path="/playground" element={<PlaygroundPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/mcp" element={<MCPPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/monitoring" element={<MonitoringPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
