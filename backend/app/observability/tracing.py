"""Tracing and Prometheus metrics."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generator

from prometheus_client import Counter, Histogram

from app.core.config import get_settings
from app.core.pricing import estimate_cost

# ---- Prometheus metrics (bounded labels only) ----

agent_requests_total = Counter(
    "agent_requests_total",
    "Total agent chat requests",
    ["agent_name", "status"],
)
agent_request_latency_seconds = Histogram(
    "agent_request_latency_seconds",
    "Agent request latency in seconds",
    ["agent_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent errors",
    ["agent_name", "error_type"],
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "status"],
)
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens",
    ["provider", "model", "direction"],
)
llm_cost_total = Counter(
    "llm_cost_total",
    "Estimated LLM cost in USD",
    ["provider", "model"],
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool calls",
    ["tool", "status"],
)
tool_errors_total = Counter(
    "tool_errors_total",
    "Total tool errors",
    ["tool"],
)
tool_latency_seconds = Histogram(
    "tool_latency_seconds",
    "Tool call latency",
    ["tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

rag_requests_total = Counter(
    "rag_requests_total",
    "Total RAG retrievals",
    ["status"],
)
rag_latency_seconds = Histogram(
    "rag_latency_seconds",
    "RAG retrieval latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

guardrail_failures_total = Counter(
    "guardrail_failures_total",
    "Guardrail failures",
    ["guardrail", "stage"],
)


@dataclass
class SpanRecord:
    span_id: str
    parent_span_id: str | None
    span_type: str
    name: str
    start_time: datetime
    end_time: datetime | None = None
    latency_ms: float = 0.0
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceContext:
    trace_id: str
    agent_id: str
    agent_version_id: str
    conversation_id: str | None = None
    spans: list[SpanRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    selected_provider: str | None = None
    selected_model: str | None = None
    fallback_used: bool = False
    status: str = "running"
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    @property
    def latency_ms(self) -> float:
        if not self.ended_at:
            return (datetime.utcnow() - self.started_at).total_seconds() * 1000
        return (self.ended_at - self.started_at).total_seconds() * 1000

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class Tracer:
    def start_trace(
        self,
        agent_id: str,
        agent_version_id: str,
        conversation_id: str | None = None,
    ) -> TraceContext:
        return TraceContext(
            trace_id=str(uuid.uuid4()),
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            conversation_id=conversation_id,
        )

    @contextmanager
    def span(
        self,
        ctx: TraceContext,
        span_type: str,
        name: str,
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[SpanRecord, None, None]:
        settings = get_settings()
        meta = dict(metadata or {})
        if not settings.log_full_prompts:
            meta.pop("prompt", None)
            meta.pop("messages", None)
        record = SpanRecord(
            span_id=str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            span_type=span_type,
            name=name,
            start_time=datetime.utcnow(),
            metadata=meta,
        )
        start = time.perf_counter()
        try:
            yield record
            record.success = True
        except Exception as exc:
            record.success = False
            record.metadata["error"] = str(exc)
            raise
        finally:
            record.end_time = datetime.utcnow()
            record.latency_ms = (time.perf_counter() - start) * 1000
            ctx.spans.append(record)

    def record_llm_usage(
        self,
        ctx: TraceContext,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        success: bool = True,
        fallback_used: bool = False,
    ) -> dict[str, float]:
        costs = estimate_cost(provider, model, input_tokens, output_tokens)
        ctx.total_input_tokens += input_tokens
        ctx.total_output_tokens += output_tokens
        ctx.estimated_cost_usd += costs["estimated_total_cost_usd"]
        ctx.selected_provider = provider
        ctx.selected_model = model
        ctx.fallback_used = ctx.fallback_used or fallback_used

        status = "success" if success else "error"
        llm_requests_total.labels(provider=provider, model=model, status=status).inc()
        llm_tokens_total.labels(provider=provider, model=model, direction="input").inc(
            input_tokens
        )
        llm_tokens_total.labels(provider=provider, model=model, direction="output").inc(
            output_tokens
        )
        llm_cost_total.labels(provider=provider, model=model).inc(
            costs["estimated_total_cost_usd"]
        )
        return costs

    def finish(self, ctx: TraceContext, status: str = "success", error: str | None = None) -> None:
        ctx.status = status
        ctx.error = error
        ctx.ended_at = datetime.utcnow()


_tracer = Tracer()


def get_tracer() -> Tracer:
    return _tracer
