"""Tool registry and built-in tools."""

from __future__ import annotations

import ast
import operator
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import ToolExecutionError, ValidationError


@dataclass
class ToolResult:
    success: bool
    output: Any
    error: str | None = None
    latency_ms: float = 0.0


class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        ...


# Safe calculator — no eval of arbitrary code
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValidationError("Unsupported expression in calculator")


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a basic arithmetic expression safely (no code execution)."
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Arithmetic expression"}
        },
        "required": ["expression"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import time

        start = time.perf_counter()
        expr = str(kwargs.get("expression", "")).strip()
        if not expr or not re.fullmatch(r"[0-9+\-*/().%\s]+", expr):
            return ToolResult(
                False, None, "Invalid expression", (time.perf_counter() - start) * 1000
            )
        try:
            tree = ast.parse(expr, mode="eval")
            value = _safe_eval(tree)
            return ToolResult(True, {"result": value}, None, (time.perf_counter() - start) * 1000)
        except Exception as exc:
            return ToolResult(False, None, str(exc), (time.perf_counter() - start) * 1000)


class WebSearchTool(BaseTool):
    """Abstraction — returns structured mock results unless a search API is configured."""

    name = "web_search"
    description = "Search the web for information (abstraction; mock results in local mode)."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import time

        start = time.perf_counter()
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 3))
        results = [
            {
                "title": f"Result {i+1} for '{query}'",
                "url": f"https://example.com/search?q={query.replace(' ', '+')}&r={i+1}",
                "snippet": f"Mock search snippet {i+1} about {query}.",
            }
            for i in range(max_results)
        ]
        return ToolResult(
            True,
            {"query": query, "results": results, "source": "mock"},
            None,
            (time.perf_counter() - start) * 1000,
        )


class WeatherTool(BaseTool):
    name = "weather"
    description = "Get current weather for a city (abstraction; mock data in local mode)."
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import time

        start = time.perf_counter()
        city = str(kwargs.get("city", "Unknown")).strip()
        # Deterministic mock based on city hash
        seed = sum(ord(c) for c in city.lower())
        temp_c = 10 + (seed % 25)
        conditions = ["clear", "cloudy", "rain", "partly cloudy"][seed % 4]
        return ToolResult(
            True,
            {
                "city": city,
                "temperature_c": temp_c,
                "conditions": conditions,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source": "mock",
            },
            None,
            (time.perf_counter() - start) * 1000,
        )


class DatabaseQueryTool(BaseTool):
    """Safe read-only query tool against an allowlisted in-memory dataset."""

    name = "database_query"
    description = (
        "Run a constrained read-only lookup against the demo knowledge table. "
        "Supports keys: agents, models, tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "table": {"type": "string", "enum": ["agents", "models", "tools"]},
            "filter_key": {"type": "string"},
        },
        "required": ["table"],
    }

    _DATA = {
        "agents": [
            {"name": "support-bot", "status": "production"},
            {"name": "research-assistant", "status": "staging"},
        ],
        "models": [
            {"provider": "openai", "model": "gpt-4o-mini"},
            {"provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
        ],
        "tools": [
            {"name": "calculator"},
            {"name": "web_search"},
            {"name": "weather"},
        ],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import time

        start = time.perf_counter()
        table = kwargs.get("table")
        if table not in self._DATA:
            return ToolResult(
                False, None, f"Table not allowlisted: {table}", (time.perf_counter() - start) * 1000
            )
        rows = self._DATA[table]
        fk = kwargs.get("filter_key")
        if fk:
            rows = [r for r in rows if fk.lower() in str(r).lower()]
        return ToolResult(True, {"rows": rows}, None, (time.perf_counter() - start) * 1000)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolExecutionError(f"Tool not found: {name}", tool=name)
        return self._tools[name]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def available_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        # Validate required fields
        required = tool.input_schema.get("required", [])
        for field_name in required:
            if field_name not in arguments:
                raise ValidationError(f"Missing required field: {field_name}")
        return await tool.execute(**arguments)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (CalculatorTool(), WebSearchTool(), WeatherTool(), DatabaseQueryTool()):
        registry.register(tool)
    return registry


_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = build_default_tool_registry()
    return _tool_registry
