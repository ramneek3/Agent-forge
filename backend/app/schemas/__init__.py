"""Pydantic API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models import RoutingStrategy, VersionStatus


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful production AI agent."
    model_provider: str = "mock"
    model: str = "mock-smart"
    temperature: float = 0.2
    routing_strategy: RoutingStrategy = RoutingStrategy.MANUAL
    fallback_provider: Optional[str] = "mock"
    fallback_model: Optional[str] = "mock-fast"
    tools: list[str] = Field(default_factory=lambda: ["calculator", "weather", "web_search", "database_query"])
    mcp_config: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "server_name": "github"}
    )
    rag_config: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "top_k": 5, "similarity_threshold": 0.35}
    )
    guardrail_config: dict[str, Any] = Field(
        default_factory=lambda: {"require_grounding": False, "blocked_patterns": []}
    )


class AgentUpdate(BaseModel):
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    routing_strategy: Optional[RoutingStrategy] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    tools: Optional[list[str]] = None
    mcp_config: Optional[dict[str, Any]] = None
    rag_config: Optional[dict[str, Any]] = None
    guardrail_config: Optional[dict[str, Any]] = None


class AgentVersionOut(BaseModel):
    id: str
    agent_id: str
    version_number: int
    status: VersionStatus
    system_prompt: str
    model_provider: str
    model: str
    temperature: float
    routing_strategy: RoutingStrategy
    fallback_provider: Optional[str]
    fallback_model: Optional[str]
    tools: list[Any]
    mcp_config: dict[str, Any]
    rag_config: dict[str, Any]
    guardrail_config: dict[str, Any]
    created_at: datetime
    promoted_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    production_version_id: Optional[str]
    request_count: int
    current_version: Optional[AgentVersionOut] = None

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    force_primary_failure: bool = False  # for fallback demos


class ChatResponse(BaseModel):
    answer: str
    agent_id: str
    agent_version: int
    agent_version_id: str
    model: str
    provider: str
    trace_id: str
    token_usage: dict[str, int]
    estimated_cost: dict[str, float]
    latency_ms: float
    citations: list[dict[str, Any]] = Field(default_factory=list)
    conversation_id: str
    fallback_used: bool = False
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    mcp_results: list[dict[str, Any]] = Field(default_factory=list)
    guardrail_results: list[dict[str, Any]] = Field(default_factory=list)


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    page_count: int
    chunk_count: int
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    similarity_threshold: float = 0.35
    document_ids: Optional[list[str]] = None


class KnowledgeSearchHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    text: str
    page_number: Optional[int]
    score: float


class PromoteRequest(BaseModel):
    target_status: VersionStatus
    notes: str = ""


class RollbackRequest(BaseModel):
    version_id: str
    notes: str = ""


class MCPServerOut(BaseModel):
    id: str
    name: str
    transport: str
    endpoint: str
    status: str
    tools: list[dict[str, Any]]
    enabled_tools: list[str]


class MCPEnableToolsRequest(BaseModel):
    enabled_tools: list[str]


class EvaluationRunRequest(BaseModel):
    agent_id: str
    name: str = "default-eval"
    dataset: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {
                "question": "What is AgentForge?",
                "expected_answer": "AgentForge is a production AI agent platform",
                "expected_source": None,
            }
        ]
    )


class EvaluationOut(BaseModel):
    id: str
    agent_id: str
    agent_version_id: str
    name: str
    status: str
    metrics: dict[str, Any]
    results: list[Any]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TraceSpanOut(BaseModel):
    id: str
    span_type: str
    name: str
    latency_ms: float
    success: bool
    metadata_json: dict[str, Any]
    start_time: datetime
    end_time: Optional[datetime]

    model_config = {"from_attributes": True}


class TraceOut(BaseModel):
    id: str
    agent_id: str
    agent_version_id: str
    conversation_id: Optional[str]
    status: str
    latency_ms: float
    total_tokens: int
    estimated_cost_usd: float
    error: Optional[str]
    created_at: datetime
    spans: list[TraceSpanOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    active_agents: int
    production_agents: int
    requests_today: int
    average_latency_ms: float
    tokens_used: int
    estimated_cost_usd: float
    error_rate: float
    latest_evaluations: list[dict[str, Any]]
