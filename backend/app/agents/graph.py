"""LangGraph agent runtime with explicit state and conditional edges."""

from __future__ import annotations

import re
import time
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.core.exceptions import GuardrailError
from app.guardrails.service import GuardrailService
from app.llm.router import ModelRouter
from app.mcp.client import MCPRegistry, get_mcp_registry
from app.observability.tracing import get_tracer
from app.rag.service import RAGService, RetrievedChunk, get_rag_service
from app.tools.registry import ToolRegistry, get_tool_registry


class AgentState(TypedDict, total=False):
    user_query: str
    messages: list[dict[str, str]]
    system_prompt: str
    needs_rag: bool
    retrieved_documents: list[dict[str, Any]]
    needs_tool: bool
    tool_name: str | None
    tool_args: dict[str, Any]
    tool_results: list[dict[str, Any]]
    needs_mcp: bool
    mcp_server: str | None
    mcp_tool: str | None
    mcp_args: dict[str, Any]
    mcp_results: list[dict[str, Any]]
    selected_provider: str
    selected_model: str
    routing_strategy: str
    fallback_provider: str | None
    fallback_model: str | None
    temperature: float
    token_usage: dict[str, int]
    cost: dict[str, float]
    trace_id: str
    errors: list[str]
    final_answer: str
    citations: list[dict[str, Any]]
    guardrail_results: list[dict[str, Any]]
    iteration: int
    classification: str
    enabled_tools: list[str]
    rag_config: dict[str, Any]
    guardrail_config: dict[str, Any]
    mcp_config: dict[str, Any]
    force_primary_failure: bool
    fallback_used: bool


class AgentRuntime:
    """Builds and runs the LangGraph agent workflow."""

    def __init__(
        self,
        router: ModelRouter | None = None,
        tools: ToolRegistry | None = None,
        rag: RAGService | None = None,
        mcp: MCPRegistry | None = None,
    ):
        self.router = router or ModelRouter()
        self.tools = tools or get_tool_registry()
        self.rag = rag or get_rag_service()
        self.mcp = mcp or get_mcp_registry()
        self.tracer = get_tracer()
        self.max_iterations = get_settings().max_agent_iterations
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("classify", self._classify)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("reason", self._reason)
        graph.add_node("execute_tool", self._execute_tool)
        graph.add_node("execute_mcp", self._execute_mcp)
        graph.add_node("generate", self._generate)
        graph.add_node("guardrails", self._guardrails)

        graph.add_edge(START, "classify")
        graph.add_conditional_edges(
            "classify",
            self._route_after_classify,
            {"retrieve": "retrieve", "reason": "reason"},
        )
        graph.add_edge("retrieve", "reason")
        graph.add_conditional_edges(
            "reason",
            self._route_after_reason,
            {
                "tool": "execute_tool",
                "mcp": "execute_mcp",
                "generate": "generate",
            },
        )
        graph.add_conditional_edges(
            "execute_tool",
            self._route_after_tool,
            {"reason": "reason", "generate": "generate"},
        )
        graph.add_conditional_edges(
            "execute_mcp",
            self._route_after_tool,
            {"reason": "reason", "generate": "generate"},
        )
        graph.add_edge("generate", "guardrails")
        graph.add_edge("guardrails", END)
        return graph.compile()

    async def _classify(self, state: AgentState) -> AgentState:
        query = state["user_query"].lower()
        rag_cfg = state.get("rag_config") or {}
        rag_enabled = rag_cfg.get("enabled", True)

        needs_rag = False
        if rag_enabled:
            rag_keywords = (
                "document",
                "pdf",
                "according",
                "knowledge",
                "cite",
                "source",
                "what does",
                "based on",
                "policy",
                "manual",
            )
            needs_rag = any(k in query for k in rag_keywords) or bool(
                rag_cfg.get("always_retrieve")
            )

        classification = "rag" if needs_rag else "general"
        if any(k in query for k in ("calculate", "weather", "search web", "database")):
            classification = "tool"
        if any(k in query for k in ("github", "repository", "pull request", "issues")):
            classification = "mcp"

        return {
            **state,
            "needs_rag": needs_rag,
            "classification": classification,
            "iteration": state.get("iteration", 0),
            "messages": state.get("messages")
            or [{"role": "user", "content": state["user_query"]}],
            "tool_results": state.get("tool_results") or [],
            "mcp_results": state.get("mcp_results") or [],
            "errors": state.get("errors") or [],
            "citations": state.get("citations") or [],
            "token_usage": state.get("token_usage")
            or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "cost": state.get("cost")
            or {
                "estimated_input_cost_usd": 0.0,
                "estimated_output_cost_usd": 0.0,
                "estimated_total_cost_usd": 0.0,
            },
        }

    def _route_after_classify(self, state: AgentState) -> Literal["retrieve", "reason"]:
        return "retrieve" if state.get("needs_rag") else "reason"

    async def _retrieve(self, state: AgentState) -> AgentState:
        # Retrieval is injected by the service layer with db session via preloaded docs
        # If already retrieved, keep; otherwise leave empty for service to fill.
        return state

    async def _reason(self, state: AgentState) -> AgentState:
        query = state["user_query"].lower()
        enabled = set(state.get("enabled_tools") or self.tools.available_names())
        needs_tool = False
        tool_name = None
        tool_args: dict[str, Any] = {}

        # Avoid re-calling the same tool endlessly
        already = {r.get("tool") for r in (state.get("tool_results") or [])}

        if "calculator" in enabled and "calculator" not in already:
            m = re.search(r"calculate\s+([0-9+\-*/().%\s]+)", query, re.I)
            if m or re.search(r"\b\d+\s*[\+\-\*/]\s*\d+", query):
                needs_tool = True
                tool_name = "calculator"
                expr = m.group(1).strip() if m else re.search(
                    r"(\d+\s*[\+\-\*/]\s*\d+(?:\s*[\+\-\*/]\s*\d+)*)", query
                )
                tool_args = {"expression": (expr if isinstance(expr, str) else expr.group(1)) if expr else "1+1"}

        if not needs_tool and "weather" in enabled and "weather" not in already:
            if "weather" in query:
                needs_tool = True
                tool_name = "weather"
                m = re.search(r"weather\s+(?:in\s+)?([A-Za-z\s]+)", query, re.I)
                tool_args = {"city": m.group(1).strip() if m else "San Francisco"}

        if not needs_tool and "web_search" in enabled and "web_search" not in already:
            if "search web" in query or "search the web" in query:
                needs_tool = True
                tool_name = "web_search"
                tool_args = {"query": state["user_query"]}

        if not needs_tool and "database_query" in enabled and "database_query" not in already:
            if "database" in query or "query table" in query:
                needs_tool = True
                tool_name = "database_query"
                table = "agents"
                for t in ("agents", "models", "tools"):
                    if t in query:
                        table = t
                tool_args = {"table": table}

        # MCP detection
        needs_mcp = False
        mcp_tool = None
        mcp_args: dict[str, Any] = {}
        mcp_cfg = state.get("mcp_config") or {}
        already_mcp = {r.get("tool") for r in (state.get("mcp_results") or [])}
        if mcp_cfg.get("enabled", True) and not already_mcp:
            if "list issues" in query or "github issues" in query:
                needs_mcp, mcp_tool = True, "list_issues"
                mcp_args = {"owner": "acme", "repo": "agentforge"}
            elif "pull request" in query or "list prs" in query:
                needs_mcp, mcp_tool = True, "list_pull_requests"
                mcp_args = {"owner": "acme", "repo": "agentforge"}
            elif "repository" in query or "github repo" in query:
                needs_mcp, mcp_tool = True, "get_repository"
                mcp_args = {"owner": "acme", "repo": "agentforge"}
            elif "search code" in query:
                needs_mcp, mcp_tool = True, "search_code"
                mcp_args = {"owner": "acme", "repo": "agentforge", "query": state["user_query"]}

        return {
            **state,
            "needs_tool": needs_tool,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "needs_mcp": needs_mcp,
            "mcp_server": mcp_cfg.get("server_name", "github"),
            "mcp_tool": mcp_tool,
            "mcp_args": mcp_args,
            "iteration": state.get("iteration", 0) + 1,
        }

    def _route_after_reason(
        self, state: AgentState
    ) -> Literal["tool", "mcp", "generate"]:
        if state.get("iteration", 0) > self.max_iterations:
            return "generate"
        if state.get("needs_tool"):
            return "tool"
        if state.get("needs_mcp"):
            return "mcp"
        return "generate"

    async def _execute_tool(self, state: AgentState) -> AgentState:
        name = state.get("tool_name")
        args = state.get("tool_args") or {}
        results = list(state.get("tool_results") or [])
        if not name:
            return {**state, "needs_tool": False}
        start = time.perf_counter()
        try:
            result = await self.tools.execute(name, args)
            results.append(
                {
                    "tool": name,
                    "args": args,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "latency_ms": result.latency_ms or (time.perf_counter() - start) * 1000,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tool": name,
                    "args": args,
                    "success": False,
                    "output": None,
                    "error": str(exc),
                    "latency_ms": (time.perf_counter() - start) * 1000,
                }
            )
        return {**state, "tool_results": results, "needs_tool": False}

    async def _execute_mcp(self, state: AgentState) -> AgentState:
        tool = state.get("mcp_tool")
        args = state.get("mcp_args") or {}
        results = list(state.get("mcp_results") or [])
        server_name = state.get("mcp_server") or "github"
        if not tool:
            return {**state, "needs_mcp": False}
        try:
            server = self.mcp.find_by_name(server_name)
            if not server:
                raise RuntimeError(f"MCP server not found: {server_name}")
            output = await self.mcp.execute_tool(server.id, tool, args)
            results.append(
                {
                    "server": server_name,
                    "tool": tool,
                    "args": args,
                    "success": True,
                    "output": output,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "server": server_name,
                    "tool": tool,
                    "args": args,
                    "success": False,
                    "error": str(exc),
                }
            )
        return {**state, "mcp_results": results, "needs_mcp": False}

    def _route_after_tool(self, state: AgentState) -> Literal["reason", "generate"]:
        if state.get("iteration", 0) >= self.max_iterations:
            return "generate"
        # One more reason pass to incorporate tool results, then generate
        if state.get("iteration", 0) <= 2 and (
            state.get("tool_results") or state.get("mcp_results")
        ):
            # If we just executed, go generate with tool context (avoid infinite loop)
            return "generate"
        return "generate"

    async def _generate(self, state: AgentState) -> AgentState:
        system = state.get("system_prompt") or "You are a helpful AI agent."
        context_parts: list[str] = []

        docs = state.get("retrieved_documents") or []
        if docs:
            context_parts.append("Retrieved context:")
            for i, d in enumerate(docs, 1):
                context_parts.append(
                    f"[{i}] ({d.get('filename')} p.{d.get('page_number')}) {d.get('text', '')[:500]}"
                )

        if state.get("tool_results"):
            context_parts.append(f"Tool results: {state['tool_results']}")
        if state.get("mcp_results"):
            context_parts.append(f"MCP results: {state['mcp_results']}")

        # Retrieval and tools have already run by this step; real models otherwise
        # tend to emit their own tool-call JSON instead of answering.
        final_step = (
            "\n\nAny retrieval and tool calls have already been done and their results are "
            "below. Answer the user directly in plain prose. Do not output tool calls or JSON."
        )
        messages = [
            {
                "role": "system",
                "content": system
                + final_step
                + ("\n\nContext:\n" + "\n".join(context_parts) if context_parts else ""),
            },
            {"role": "user", "content": state["user_query"]},
        ]

        result, decision = await self.router.generate(
            messages,
            strategy=state.get("routing_strategy") or "MANUAL",
            provider=state.get("selected_provider") or "mock",
            model=state.get("selected_model") or "mock-smart",
            fallback_provider=state.get("fallback_provider"),
            fallback_model=state.get("fallback_model"),
            temperature=float(state.get("temperature") or 0.2),
            force_primary_failure=bool(state.get("force_primary_failure")),
        )

        answer = result.content
        # If mock returned TOOL_CALL leftover, strip and use tool results
        if answer.startswith("TOOL_CALL:") and state.get("tool_results"):
            tr = state["tool_results"][-1]
            answer = f"I used the {tr.get('tool')} tool. Result: {tr.get('output')}"

        citations = []
        for d in docs:
            citations.append(
                {
                    "document_id": d.get("document_id"),
                    "filename": d.get("filename"),
                    "page_number": d.get("page_number"),
                    "score": d.get("score"),
                    "snippet": (d.get("text") or "")[:200],
                }
            )

        # Enrich answer with citations if RAG used
        if citations and "[citation" not in answer.lower() and "based on" not in answer.lower():
            cite_str = ", ".join(
                f"{c['filename']} (p.{c['page_number']})" for c in citations[:3]
            )
            answer = f"{answer}\n\nSources: {cite_str}"

        token_usage = {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        }
        from app.core.pricing import estimate_cost

        cost = estimate_cost(
            decision.provider,
            decision.model,
            result.usage.input_tokens,
            result.usage.output_tokens,
        )

        return {
            **state,
            "final_answer": answer,
            "citations": citations,
            "selected_provider": decision.provider,
            "selected_model": decision.model,
            "fallback_used": decision.fallback_used,
            "token_usage": token_usage,
            "cost": cost,
            "messages": messages + [{"role": "assistant", "content": answer}],
            "_llm_latency_ms": result.latency_ms,
            "_route_decision": {
                "strategy": decision.strategy,
                "attempted": decision.attempted,
                "fallback_used": decision.fallback_used,
            },
        }

    async def _guardrails(self, state: AgentState) -> AgentState:
        svc = GuardrailService(state.get("guardrail_config"))
        input_results = svc.check_input(state["user_query"])
        output_results = svc.check_output(
            state.get("final_answer") or "",
            used_rag=bool(state.get("retrieved_documents")),
            citations=state.get("citations"),
        )
        all_results = input_results + output_results
        serialized = [
            {
                "passed": r.passed,
                "name": r.name,
                "message": r.message,
                "details": r.details,
            }
            for r in all_results
        ]
        failures = [r for r in all_results if not r.passed]
        if failures:
            # Controlled error — surface in state
            return {
                **state,
                "guardrail_results": serialized,
                "errors": (state.get("errors") or [])
                + [f"guardrail:{failures[0].name}:{failures[0].message}"],
                "final_answer": (
                    state.get("final_answer")
                    if failures[0].name not in ("prompt_injection", "blocked_pattern", "prompt_length")
                    else "Request blocked by guardrails."
                ),
            }
        return {**state, "guardrail_results": serialized}

    async def run(self, initial: AgentState) -> AgentState:
        # Input guardrails before graph
        svc = GuardrailService(initial.get("guardrail_config"))
        input_check = svc.check_input(initial["user_query"])
        try:
            svc.assert_all_passed(input_check)
        except GuardrailError as exc:
            return {
                **initial,
                "final_answer": "Request blocked by guardrails.",
                "errors": [f"guardrail:{exc.guardrail}:{exc.message}"],
                "guardrail_results": [
                    {"passed": r.passed, "name": r.name, "message": r.message, "details": r.details}
                    for r in input_check
                ],
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "cost": {
                    "estimated_input_cost_usd": 0.0,
                    "estimated_output_cost_usd": 0.0,
                    "estimated_total_cost_usd": 0.0,
                },
                "citations": [],
                "tool_results": [],
                "mcp_results": [],
            }

        result = await self._graph.ainvoke(initial)
        return result


def documents_to_state(docs: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": d.chunk_id,
            "document_id": d.document_id,
            "filename": d.filename,
            "text": d.text,
            "page_number": d.page_number,
            "score": d.score,
            "metadata": d.metadata,
        }
        for d in docs
    ]
