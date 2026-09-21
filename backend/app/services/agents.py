"""Agent service: CRUD, versioning, chat orchestration."""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import AgentRuntime, documents_to_state
from app.core.exceptions import GuardrailError, NotFoundError, ValidationError
from app.models import (
    Agent,
    AgentVersion,
    Conversation,
    Deployment,
    LLMCall,
    Message,
    Trace,
    TraceSpan,
    UsageRecord,
    VersionStatus,
)
from app.observability.tracing import (
    agent_errors_total,
    agent_request_latency_seconds,
    agent_requests_total,
    get_tracer,
    guardrail_failures_total,
    rag_latency_seconds,
    rag_requests_total,
    tool_calls_total,
    tool_errors_total,
    tool_latency_seconds,
)
from app.rag.service import get_rag_service
from app.schemas import AgentCreate, AgentUpdate, ChatRequest, ChatResponse


class AgentService:
    def __init__(self, runtime: AgentRuntime | None = None):
        self.runtime = runtime or AgentRuntime()
        self.tracer = get_tracer()
        self.rag = get_rag_service()

    async def create_agent(self, db: AsyncSession, payload: AgentCreate) -> Agent:
        existing = await db.execute(select(Agent).where(Agent.name == payload.name))
        if existing.scalar_one_or_none():
            raise ValidationError(f"Agent name already exists: {payload.name}")

        agent = Agent(id=str(uuid.uuid4()), name=payload.name, description=payload.description)
        db.add(agent)
        await db.flush()

        version = AgentVersion(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            version_number=1,
            status=VersionStatus.draft,
            system_prompt=payload.system_prompt,
            model_provider=payload.model_provider,
            model=payload.model,
            temperature=payload.temperature,
            routing_strategy=payload.routing_strategy,
            fallback_provider=payload.fallback_provider,
            fallback_model=payload.fallback_model,
            tools=payload.tools,
            mcp_config=payload.mcp_config,
            rag_config=payload.rag_config,
            guardrail_config=payload.guardrail_config,
        )
        db.add(version)
        await db.flush()
        await db.refresh(agent)
        return agent

    async def list_agents(self, db: AsyncSession) -> list[Agent]:
        result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
        return list(result.scalars().all())

    async def get_agent(self, db: AsyncSession, agent_id: str) -> Agent:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise NotFoundError(f"Agent not found: {agent_id}")
        return agent

    async def get_versions(self, db: AsyncSession, agent_id: str) -> list[AgentVersion]:
        result = await db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(self, db: AsyncSession, version_id: str) -> AgentVersion:
        result = await db.execute(select(AgentVersion).where(AgentVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundError(f"Version not found: {version_id}")
        return version

    async def create_new_version(
        self, db: AsyncSession, agent_id: str, updates: AgentUpdate
    ) -> AgentVersion:
        agent = await self.get_agent(db, agent_id)
        versions = await self.get_versions(db, agent_id)
        latest = versions[0] if versions else None
        next_num = (latest.version_number + 1) if latest else 1

        base = latest
        version = AgentVersion(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            version_number=next_num,
            status=VersionStatus.draft,
            system_prompt=updates.system_prompt or (base.system_prompt if base else ""),
            model_provider=updates.model_provider or (base.model_provider if base else "mock"),
            model=updates.model or (base.model if base else "mock-smart"),
            temperature=updates.temperature if updates.temperature is not None else (base.temperature if base else 0.2),
            routing_strategy=updates.routing_strategy or (base.routing_strategy if base else None),
            fallback_provider=updates.fallback_provider if updates.fallback_provider is not None else (base.fallback_provider if base else None),
            fallback_model=updates.fallback_model if updates.fallback_model is not None else (base.fallback_model if base else None),
            tools=updates.tools if updates.tools is not None else (base.tools if base else []),
            mcp_config=updates.mcp_config if updates.mcp_config is not None else (base.mcp_config if base else {}),
            rag_config=updates.rag_config if updates.rag_config is not None else (base.rag_config if base else {}),
            guardrail_config=updates.guardrail_config if updates.guardrail_config is not None else (base.guardrail_config if base else {}),
        )
        if updates.description is not None:
            agent.description = updates.description
        db.add(version)
        await db.flush()
        return version

    async def promote_version(
        self,
        db: AsyncSession,
        agent_id: str,
        version_id: str,
        target: VersionStatus,
        notes: str = "",
    ) -> AgentVersion:
        agent = await self.get_agent(db, agent_id)
        version = await self.get_version(db, version_id)
        if version.agent_id != agent_id:
            raise ValidationError("Version does not belong to agent")

        allowed = {
            VersionStatus.draft: {VersionStatus.staging},
            VersionStatus.staging: {VersionStatus.production},
            VersionStatus.production: {VersionStatus.archived},
        }
        if target not in allowed.get(version.status, set()):
            raise ValidationError(
                f"Cannot promote from {version.status.value} to {target.value}"
            )

        from_id = agent.production_version_id
        if target == VersionStatus.production:
            # Archive current production
            if agent.production_version_id:
                current = await self.get_version(db, agent.production_version_id)
                current.status = VersionStatus.archived
            version.status = VersionStatus.production
            version.promoted_at = datetime.utcnow()
            agent.production_version_id = version.id
        else:
            version.status = target
            if target == VersionStatus.staging:
                version.promoted_at = datetime.utcnow()

        db.add(
            Deployment(
                agent_id=agent_id,
                from_version_id=from_id,
                to_version_id=version.id,
                action=f"promote_to_{target.value}",
                notes=notes,
            )
        )
        await db.flush()
        return version

    async def rollback(
        self, db: AsyncSession, agent_id: str, version_id: str, notes: str = ""
    ) -> AgentVersion:
        agent = await self.get_agent(db, agent_id)
        target = await self.get_version(db, version_id)
        if target.agent_id != agent_id:
            raise ValidationError("Version does not belong to agent")

        # Do not overwrite — re-activate a prior version as production
        prev_prod = agent.production_version_id
        if prev_prod:
            current = await self.get_version(db, prev_prod)
            current.status = VersionStatus.archived

        target.status = VersionStatus.production
        target.promoted_at = datetime.utcnow()
        agent.production_version_id = target.id

        db.add(
            Deployment(
                agent_id=agent_id,
                from_version_id=prev_prod,
                to_version_id=target.id,
                action="rollback",
                notes=notes,
            )
        )
        await db.flush()
        return target

    async def resolve_active_version(
        self, db: AsyncSession, agent: Agent
    ) -> AgentVersion:
        if agent.production_version_id:
            return await self.get_version(db, agent.production_version_id)
        versions = await self.get_versions(db, agent.id)
        if not versions:
            raise NotFoundError("Agent has no versions")
        # Prefer staging, else latest draft
        for v in versions:
            if v.status == VersionStatus.staging:
                return v
        return versions[0]

    async def chat(
        self, db: AsyncSession, agent_id: str, payload: ChatRequest
    ) -> ChatResponse:
        agent = await self.get_agent(db, agent_id)
        version = await self.resolve_active_version(db, agent)
        start = time.perf_counter()

        # Conversation
        if payload.conversation_id:
            conv_result = await db.execute(
                select(Conversation).where(Conversation.id == payload.conversation_id)
            )
            conversation = conv_result.scalar_one_or_none()
            if not conversation:
                raise NotFoundError("Conversation not found")
        else:
            conversation = Conversation(
                id=str(uuid.uuid4()),
                agent_id=agent.id,
                agent_version_id=version.id,
            )
            db.add(conversation)
            await db.flush()

        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=payload.message,
            )
        )

        trace_ctx = self.tracer.start_trace(agent.id, version.id, conversation.id)

        try:
            with self.tracer.span(trace_ctx, "agent", "Agent start"):
                pass

            retrieved_docs: list[dict] = []
            rag_cfg = version.rag_config or {}
            needs_rag_hint = rag_cfg.get("enabled", True) and any(
                k in payload.message.lower()
                for k in ("document", "pdf", "according", "knowledge", "cite", "source", "policy", "what is", "based on")
            ) or rag_cfg.get("always_retrieve")

            if needs_rag_hint or rag_cfg.get("always_retrieve"):
                rag_start = time.perf_counter()
                with self.tracer.span(trace_ctx, "rag", "RAG retrieval") as span:
                    docs = await self.rag.search(
                        db,
                        payload.message,
                        top_k=int(rag_cfg.get("top_k", 5)),
                        similarity_threshold=float(rag_cfg.get("similarity_threshold", 0.35)),
                    )
                    retrieved_docs = documents_to_state(docs)
                    span.metadata["hit_count"] = len(retrieved_docs)
                rag_requests_total.labels(status="success").inc()
                rag_latency_seconds.observe(time.perf_counter() - rag_start)

            initial = {
                "user_query": payload.message,
                "system_prompt": version.system_prompt,
                "selected_provider": version.model_provider,
                "selected_model": version.model,
                "routing_strategy": version.routing_strategy.value
                if hasattr(version.routing_strategy, "value")
                else str(version.routing_strategy),
                "fallback_provider": version.fallback_provider,
                "fallback_model": version.fallback_model,
                "temperature": version.temperature,
                "enabled_tools": version.tools or [],
                "rag_config": version.rag_config or {},
                "guardrail_config": version.guardrail_config or {},
                "mcp_config": version.mcp_config or {},
                "retrieved_documents": retrieved_docs,
                "trace_id": trace_ctx.trace_id,
                "force_primary_failure": payload.force_primary_failure,
            }

            # Trace tool/mcp/llm via wrappers around runtime result
            with self.tracer.span(trace_ctx, "agent", "LangGraph execution"):
                result = await self.runtime.run(initial)

            # Record tool spans
            for tr in result.get("tool_results") or []:
                status = "success" if tr.get("success") else "error"
                tool_calls_total.labels(tool=tr.get("tool", "unknown"), status=status).inc()
                if not tr.get("success"):
                    tool_errors_total.labels(tool=tr.get("tool", "unknown")).inc()
                tool_latency_seconds.labels(tool=tr.get("tool", "unknown")).observe(
                    (tr.get("latency_ms") or 0) / 1000.0
                )
                with self.tracer.span(
                    trace_ctx, "tool", f"Tool:{tr.get('tool')}", metadata={"result": tr}
                ):
                    pass

            for mr in result.get("mcp_results") or []:
                with self.tracer.span(
                    trace_ctx, "mcp", f"MCP:{mr.get('tool')}", metadata={"result": mr}
                ):
                    pass

            costs = self.tracer.record_llm_usage(
                trace_ctx,
                result.get("selected_provider") or version.model_provider,
                result.get("selected_model") or version.model,
                (result.get("token_usage") or {}).get("input_tokens", 0),
                (result.get("token_usage") or {}).get("output_tokens", 0),
                success=not bool(result.get("errors")),
                fallback_used=bool(result.get("fallback_used")),
            )
            with self.tracer.span(
                trace_ctx,
                "llm",
                "Model call",
                metadata={
                    "provider": result.get("selected_provider"),
                    "model": result.get("selected_model"),
                    "fallback_used": result.get("fallback_used"),
                    "tokens": result.get("token_usage"),
                    "estimated_cost": costs,
                },
            ):
                pass

            for gr in result.get("guardrail_results") or []:
                with self.tracer.span(
                    trace_ctx,
                    "guardrail",
                    f"Guardrail:{gr.get('name')}",
                    metadata=gr,
                ):
                    if not gr.get("passed"):
                        guardrail_failures_total.labels(
                            guardrail=gr.get("name", "unknown"),
                            stage="runtime",
                        ).inc()

            with self.tracer.span(trace_ctx, "response", "Final response"):
                pass

            answer = result.get("final_answer") or ""
            errors = result.get("errors") or []
            status = "error" if errors and answer.startswith("Request blocked") else "success"
            if errors and "guardrail" in errors[0]:
                status = "blocked"

            self.tracer.finish(trace_ctx, status=status, error="; ".join(errors) or None)

            # Persist message + trace
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=answer,
                    metadata_json={
                        "trace_id": trace_ctx.trace_id,
                        "citations": result.get("citations") or [],
                    },
                )
            )

            latency_ms = (time.perf_counter() - start) * 1000
            trace_row = Trace(
                id=trace_ctx.trace_id,
                agent_id=agent.id,
                agent_version_id=version.id,
                conversation_id=conversation.id,
                status=trace_ctx.status,
                latency_ms=latency_ms,
                total_tokens=trace_ctx.total_tokens,
                estimated_cost_usd=trace_ctx.estimated_cost_usd,
                error=trace_ctx.error,
            )
            db.add(trace_row)
            for sp in trace_ctx.spans:
                db.add(
                    TraceSpan(
                        id=sp.span_id,
                        trace_id=trace_ctx.trace_id,
                        parent_span_id=sp.parent_span_id,
                        span_type=sp.span_type,
                        name=sp.name,
                        start_time=sp.start_time,
                        end_time=sp.end_time,
                        latency_ms=sp.latency_ms,
                        success=sp.success,
                        metadata_json=sp.metadata,
                    )
                )

            db.add(
                LLMCall(
                    trace_id=trace_ctx.trace_id,
                    provider=result.get("selected_provider") or version.model_provider,
                    model=result.get("selected_model") or version.model,
                    input_tokens=(result.get("token_usage") or {}).get("input_tokens", 0),
                    output_tokens=(result.get("token_usage") or {}).get("output_tokens", 0),
                    total_tokens=(result.get("token_usage") or {}).get("total_tokens", 0),
                    estimated_cost_usd=trace_ctx.estimated_cost_usd,
                    latency_ms=result.get("_llm_latency_ms") or 0,
                    fallback_used=bool(result.get("fallback_used")),
                    success=status == "success",
                )
            )

            agent.request_count = (agent.request_count or 0) + 1
            await self._bump_usage(
                db,
                agent.id,
                latency_ms,
                trace_ctx.total_tokens,
                trace_ctx.estimated_cost_usd,
                error=status != "success",
            )

            agent_requests_total.labels(agent_name=agent.name, status=status).inc()
            agent_request_latency_seconds.labels(agent_name=agent.name).observe(
                latency_ms / 1000.0
            )
            if status != "success":
                agent_errors_total.labels(
                    agent_name=agent.name, error_type=status
                ).inc()

            await db.flush()

            return ChatResponse(
                answer=answer,
                agent_id=agent.id,
                agent_version=version.version_number,
                agent_version_id=version.id,
                model=result.get("selected_model") or version.model,
                provider=result.get("selected_provider") or version.model_provider,
                trace_id=trace_ctx.trace_id,
                token_usage=result.get("token_usage")
                or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                estimated_cost=result.get("cost")
                or {
                    "estimated_input_cost_usd": 0.0,
                    "estimated_output_cost_usd": 0.0,
                    "estimated_total_cost_usd": 0.0,
                },
                latency_ms=latency_ms,
                citations=result.get("citations") or [],
                conversation_id=conversation.id,
                fallback_used=bool(result.get("fallback_used")),
                tool_results=result.get("tool_results") or [],
                mcp_results=result.get("mcp_results") or [],
                guardrail_results=result.get("guardrail_results") or [],
            )

        except GuardrailError as exc:
            agent_errors_total.labels(agent_name=agent.name, error_type="guardrail").inc()
            guardrail_failures_total.labels(guardrail=exc.guardrail, stage="input").inc()
            raise
        except Exception:
            agent_errors_total.labels(agent_name=agent.name, error_type="exception").inc()
            raise

    async def _bump_usage(
        self,
        db: AsyncSession,
        agent_id: str,
        latency_ms: float,
        tokens: int,
        cost: float,
        error: bool = False,
    ) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        result = await db.execute(
            select(UsageRecord).where(
                UsageRecord.agent_id == agent_id, UsageRecord.date == today
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            row = UsageRecord(agent_id=agent_id, date=today)
            db.add(row)
        row.request_count = (row.request_count or 0) + 1
        if error:
            row.error_count = (row.error_count or 0) + 1
        row.total_tokens = (row.total_tokens or 0) + tokens
        row.estimated_cost_usd = (row.estimated_cost_usd or 0.0) + cost
        row.total_latency_ms = (row.total_latency_ms or 0.0) + latency_ms
