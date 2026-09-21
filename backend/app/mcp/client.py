"""MCP client abstraction and registry.

This is a real MCP-shaped architecture (server registration, connection,
tool discovery, listing, execution) with a local mock GitHub MCP server
for development without external OAuth credentials.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import MCPError


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPServerInfo:
    id: str
    name: str
    transport: str
    endpoint: str
    status: str
    tools: list[MCPTool] = field(default_factory=list)
    enabled_tools: list[str] = field(default_factory=list)


class MCPClient(ABC):
    """Abstract MCP client — transport-agnostic."""

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def list_tools(self) -> list[MCPTool]:
        ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...


class MockGitHubMCPClient(MCPClient):
    """Local MCP-compatible mock implementing GitHub-like tools.

    Protocol shape mirrors MCP tool discovery/execution even though the
    transport is in-process for local development.
    """

    PROTOCOL = "mcp-mock/1.0"

    def __init__(self, server_name: str = "github"):
        self.server_name = server_name
        self._connected = False
        self._tools = [
            MCPTool(
                "get_repository",
                "Get repository metadata",
                {
                    "type": "object",
                    "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}},
                    "required": ["owner", "repo"],
                },
            ),
            MCPTool(
                "list_issues",
                "List repository issues",
                {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "state": {"type": "string", "default": "open"},
                    },
                    "required": ["owner", "repo"],
                },
            ),
            MCPTool(
                "list_pull_requests",
                "List pull requests",
                {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
            ),
            MCPTool(
                "search_code",
                "Search code in a repository",
                {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["owner", "repo", "query"],
                },
            ),
        ]

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self) -> list[MCPTool]:
        if not self._connected:
            raise MCPError("MCP server not connected", server=self.server_name)
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._connected:
            raise MCPError("MCP server not connected", server=self.server_name)
        tool_names = {t.name for t in self._tools}
        if name not in tool_names:
            raise MCPError(f"Unknown MCP tool: {name}", server=self.server_name)

        owner = arguments.get("owner", "acme")
        repo = arguments.get("repo", "agentforge")

        if name == "get_repository":
            return {
                "full_name": f"{owner}/{repo}",
                "description": "AgentForge — production AI agent platform",
                "stars": 128,
                "default_branch": "main",
                "mcp_protocol": self.PROTOCOL,
            }
        if name == "list_issues":
            return {
                "issues": [
                    {"number": 12, "title": "Add streaming chat", "state": "open"},
                    {"number": 9, "title": "Improve RAG citations", "state": "open"},
                ]
            }
        if name == "list_pull_requests":
            return {
                "pull_requests": [
                    {"number": 42, "title": "feat: model fallback", "state": "open"},
                ]
            }
        if name == "search_code":
            q = arguments.get("query", "")
            return {
                "matches": [
                    {
                        "path": "backend/app/agents/graph.py",
                        "snippet": f"# match for {q}",
                    }
                ]
            }
        return {}


class MCPRegistry:
    """Registry of MCP servers available to agents."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerInfo] = {}
        self._clients: dict[str, MCPClient] = {}

    def register_server(
        self,
        name: str,
        transport: str = "mock",
        endpoint: str = "mock://github",
        server_id: str | None = None,
        enabled_tools: list[str] | None = None,
    ) -> MCPServerInfo:
        sid = server_id or str(uuid.uuid4())
        info = MCPServerInfo(
            id=sid,
            name=name,
            transport=transport,
            endpoint=endpoint,
            status="registered",
            enabled_tools=enabled_tools or [],
        )
        self._servers[sid] = info
        if transport == "mock" or name.lower() == "github":
            self._clients[sid] = MockGitHubMCPClient(name)
        else:
            # Extensibility point for real stdio/http MCP transports
            self._clients[sid] = MockGitHubMCPClient(name)
        return info

    async def connect(self, server_id: str) -> MCPServerInfo:
        if server_id not in self._servers:
            raise MCPError(f"Unknown MCP server: {server_id}")
        client = self._clients[server_id]
        await client.connect()
        tools = await client.list_tools()
        info = self._servers[server_id]
        info.status = "connected"
        info.tools = tools
        if not info.enabled_tools:
            info.enabled_tools = [t.name for t in tools]
        return info

    async def disconnect(self, server_id: str) -> None:
        if server_id in self._clients:
            await self._clients[server_id].disconnect()
            self._servers[server_id].status = "disconnected"

    def list_servers(self) -> list[MCPServerInfo]:
        return list(self._servers.values())

    def get(self, server_id: str) -> MCPServerInfo:
        if server_id not in self._servers:
            raise MCPError(f"Unknown MCP server: {server_id}")
        return self._servers[server_id]

    def set_enabled_tools(self, server_id: str, tools: list[str]) -> MCPServerInfo:
        info = self.get(server_id)
        available = {t.name for t in info.tools} or set(tools)
        info.enabled_tools = [t for t in tools if t in available or not info.tools]
        return info

    async def execute_tool(
        self, server_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        info = self.get(server_id)
        if info.status != "connected":
            await self.connect(server_id)
        if tool_name not in info.enabled_tools:
            raise MCPError(
                f"Tool '{tool_name}' is not enabled for server '{info.name}'",
                server=info.name,
            )
        start = time.perf_counter()
        result = await self._clients[server_id].call_tool(tool_name, arguments)
        result["_mcp"] = {
            "server": info.name,
            "tool": tool_name,
            "latency_ms": (time.perf_counter() - start) * 1000,
            "protocol": getattr(self._clients[server_id], "PROTOCOL", "mcp"),
        }
        return result

    def find_by_name(self, name: str) -> MCPServerInfo | None:
        for s in self._servers.values():
            if s.name.lower() == name.lower():
                return s
        return None


_mcp_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = MCPRegistry()
        # Pre-register GitHub mock MCP server
        info = _mcp_registry.register_server("github", transport="mock", endpoint="mock://github")
        # Eager connect for demo readiness will happen on startup
        _mcp_registry._default_github_id = info.id  # type: ignore[attr-defined]
    return _mcp_registry


async def ensure_default_mcp_connected() -> None:
    registry = get_mcp_registry()
    for server in registry.list_servers():
        if server.status != "connected":
            await registry.connect(server.id)
