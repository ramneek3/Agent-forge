"""ORM models for AgentForge."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class VersionStatus(str, enum.Enum):
    draft = "draft"
    staging = "staging"
    production = "production"
    archived = "archived"


class RoutingStrategy(str, enum.Enum):
    MANUAL = "MANUAL"
    CHEAPEST = "CHEAPEST"
    FASTEST = "FASTEST"
    FALLBACK = "FALLBACK"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    production_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("agent_versions.id"), nullable=True
    )
    request_count: Mapped[int] = mapped_column(Integer, default=0)

    versions: Mapped[list[AgentVersion]] = relationship(
        "AgentVersion",
        back_populates="agent",
        foreign_keys="AgentVersion.agent_id",
        cascade="all, delete-orphan",
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus), default=VersionStatus.draft
    )
    system_prompt: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(64), default="mock")
    model: Mapped[str] = mapped_column(String(128), default="mock-smart")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    routing_strategy: Mapped[RoutingStrategy] = mapped_column(
        Enum(RoutingStrategy), default=RoutingStrategy.MANUAL
    )
    fallback_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fallback_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    mcp_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rag_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    guardrail_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    agent: Mapped[Agent] = relationship(
        "Agent", back_populates="versions", foreign_keys=[agent_id]
    )


class ModelRegistry(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Stored as JSON list of floats for SQLite compatibility; pgvector used in Postgres path
    embedding: Mapped[list[Any]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")


class ToolDefinition(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    transport: Mapped[str] = mapped_column(String(64), default="stdio")  # stdio|http|mock
    endpoint: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(64), default="disconnected")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    discovered_tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    enabled_tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentTool(Base):
    __tablename__ = "agent_tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_versions.id")
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    agent_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_versions.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id")
    )
    role: Mapped[str] = mapped_column(String(32))  # user|assistant|system|tool
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_version_id: Mapped[str] = mapped_column(String(36))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    spans: Mapped[list[TraceSpan]] = relationship(
        "TraceSpan", back_populates="trace", cascade="all, delete-orphan"
    )


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trace_id: Mapped[str] = mapped_column(String(36), ForeignKey("traces.id"))
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    span_type: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    start_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    trace: Mapped[Trace] = relationship("Trace", back_populates="spans")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_version_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(255))
    dataset: Mapped[list[Any]] = mapped_column(JSON, default=list)
    results: Mapped[list[Any]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    from_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    to_version_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))  # promote|rollback|archive
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    notes: Mapped[str] = mapped_column(Text, default="")
