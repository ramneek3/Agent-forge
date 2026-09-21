"""API routers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from app.core.exceptions import AgentForgeError
from app.core.pricing import list_models
from app.core.security import require_admin
from app.db.session import get_db
from app.evaluation.runner import EvalExample, EvaluationRunner
from app.mcp.client import ensure_default_mcp_connected, get_mcp_registry
from app.models import (
    Agent,
    AgentVersion,
    Document,
    Evaluation,
    Trace,
    UsageRecord,
)
from app.rag.service import get_rag_service
from app.schemas import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    AgentVersionOut,
    ChatRequest,
    ChatResponse,
    DashboardStats,
    DocumentOut,
    EvaluationOut,
    EvaluationRunRequest,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    MCPEnableToolsRequest,
    MCPServerOut,
    PromoteRequest,
    RollbackRequest,
    TraceOut,
    TraceSpanOut,
)
from app.services.agents import AgentService
from app.tools.registry import get_tool_registry

router = APIRouter()
agent_service = AgentService()


def _http_error(exc: AgentForgeError) -> HTTPException:
    status = 404 if exc.code == "not_found" else 400
    if exc.code == "guardrail_failure":
        status = 422
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


# ---------- Health / metrics ----------


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentforge"}


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- Dashboard ----------


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    agents = (await db.execute(select(Agent))).scalars().all()
    prod = sum(1 for a in agents if a.production_version_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    usage_rows = (
        await db.execute(select(UsageRecord).where(UsageRecord.date == today))
    ).scalars().all()
    requests_today = sum(r.request_count for r in usage_rows)
    errors = sum(r.error_count for r in usage_rows)
    tokens = sum(r.total_tokens for r in usage_rows)
    cost = sum(r.estimated_cost_usd for r in usage_rows)
    latency_sum = sum(r.total_latency_ms for r in usage_rows)
    avg_latency = (latency_sum / requests_today) if requests_today else 0.0
    error_rate = (errors / requests_today) if requests_today else 0.0

    evals = (
        await db.execute(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(5))
    ).scalars().all()
    latest = [
        {
            "id": e.id,
            "name": e.name,
            "status": e.status,
            "metrics": e.metrics,
            "created_at": e.created_at.isoformat(),
        }
        for e in evals
    ]
    return DashboardStats(
        active_agents=len(agents),
        production_agents=prod,
        requests_today=requests_today,
        average_latency_ms=avg_latency,
        tokens_used=tokens,
        estimated_cost_usd=cost,
        error_rate=error_rate,
        latest_evaluations=latest,
    )


# ---------- Agents ----------


@router.post("/agents", response_model=AgentOut)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> AgentOut:
    try:
        agent = await agent_service.create_agent(db, payload)
        versions = await agent_service.get_versions(db, agent.id)
        return _agent_out(agent, versions[0] if versions else None)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[AgentOut]:
    agents = await agent_service.list_agents(db)
    out = []
    for a in agents:
        versions = await agent_service.get_versions(db, a.id)
        current = None
        if a.production_version_id:
            current = next((v for v in versions if v.id == a.production_version_id), None)
        if not current and versions:
            current = versions[0]
        out.append(_agent_out(a, current))
    return out


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> AgentOut:
    try:
        agent = await agent_service.get_agent(db, agent_id)
        versions = await agent_service.get_versions(db, agent_id)
        current = None
        if agent.production_version_id:
            current = next((v for v in versions if v.id == agent.production_version_id), None)
        if not current and versions:
            current = versions[0]
        return _agent_out(agent, current)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


@router.get("/agents/{agent_id}/versions", response_model=list[AgentVersionOut])
async def list_versions(agent_id: str, db: AsyncSession = Depends(get_db)) -> list[AgentVersionOut]:
    versions = await agent_service.get_versions(db, agent_id)
    return [AgentVersionOut.model_validate(v) for v in versions]


@router.post("/agents/{agent_id}/versions", response_model=AgentVersionOut)
async def create_version(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> AgentVersionOut:
    try:
        version = await agent_service.create_new_version(db, agent_id, payload)
        return AgentVersionOut.model_validate(version)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/versions/{version_id}/promote", response_model=AgentVersionOut)
async def promote_version(
    agent_id: str,
    version_id: str,
    payload: PromoteRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> AgentVersionOut:
    try:
        version = await agent_service.promote_version(
            db, agent_id, version_id, payload.target_status, payload.notes
        )
        return AgentVersionOut.model_validate(version)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/rollback", response_model=AgentVersionOut)
async def rollback_agent(
    agent_id: str,
    payload: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> AgentVersionOut:
    try:
        version = await agent_service.rollback(db, agent_id, payload.version_id, payload.notes)
        return AgentVersionOut.model_validate(version)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/chat", response_model=ChatResponse)
async def chat(
    agent_id: str, payload: ChatRequest, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    try:
        return await agent_service.chat(db, agent_id, payload)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc


def _agent_out(agent: Agent, version: AgentVersion | None) -> AgentOut:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        created_at=agent.created_at,
        production_version_id=agent.production_version_id,
        request_count=agent.request_count or 0,
        current_version=AgentVersionOut.model_validate(version) if version else None,
    )


# ---------- Documents / RAG ----------


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> DocumentOut:
    data = await file.read()
    rag = get_rag_service()
    filename = file.filename or "upload.bin"
    if filename.lower().endswith(".pdf"):
        doc = await rag.ingest_pdf(db, filename, data)
    else:
        doc = await rag.ingest_text(db, filename, data.decode("utf-8", errors="ignore"))
    await db.flush()
    return DocumentOut.model_validate(doc)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[DocumentOut]:
    rows = (await db.execute(select(Document).order_by(Document.created_at.desc()))).scalars().all()
    return [DocumentOut.model_validate(d) for d in rows]


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict[str, str]:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    await db.delete(doc)
    return {"status": "deleted", "id": document_id}


@router.post("/knowledge/search", response_model=list[KnowledgeSearchHit])
async def knowledge_search(
    payload: KnowledgeSearchRequest, db: AsyncSession = Depends(get_db)
) -> list[KnowledgeSearchHit]:
    rag = get_rag_service()
    hits = await rag.search(
        db,
        payload.query,
        top_k=payload.top_k,
        similarity_threshold=payload.similarity_threshold,
        document_ids=payload.document_ids,
    )
    return [
        KnowledgeSearchHit(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            filename=h.filename,
            text=h.text,
            page_number=h.page_number,
            score=h.score,
        )
        for h in hits
    ]


# ---------- Tools ----------


@router.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    return get_tool_registry().list_tools()


# ---------- MCP ----------


@router.get("/mcp/servers", response_model=list[MCPServerOut])
async def list_mcp_servers() -> list[MCPServerOut]:
    await ensure_default_mcp_connected()
    registry = get_mcp_registry()
    return [
        MCPServerOut(
            id=s.id,
            name=s.name,
            transport=s.transport,
            endpoint=s.endpoint,
            status=s.status,
            tools=[
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in s.tools
            ],
            enabled_tools=s.enabled_tools,
        )
        for s in registry.list_servers()
    ]


@router.post("/mcp/servers/{server_id}/connect", response_model=MCPServerOut)
async def connect_mcp(server_id: str) -> MCPServerOut:
    registry = get_mcp_registry()
    s = await registry.connect(server_id)
    return MCPServerOut(
        id=s.id,
        name=s.name,
        transport=s.transport,
        endpoint=s.endpoint,
        status=s.status,
        tools=[
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in s.tools
        ],
        enabled_tools=s.enabled_tools,
    )


@router.post("/mcp/servers/{server_id}/tools", response_model=MCPServerOut)
async def enable_mcp_tools(server_id: str, payload: MCPEnableToolsRequest) -> MCPServerOut:
    registry = get_mcp_registry()
    s = registry.set_enabled_tools(server_id, payload.enabled_tools)
    return MCPServerOut(
        id=s.id,
        name=s.name,
        transport=s.transport,
        endpoint=s.endpoint,
        status=s.status,
        tools=[
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in s.tools
        ],
        enabled_tools=s.enabled_tools,
    )


# ---------- Models ----------


@router.get("/models")
async def get_models() -> list[dict[str, Any]]:
    return list_models()


# ---------- Traces ----------


@router.get("/traces", response_model=list[TraceOut])
async def list_traces(limit: int = 50, db: AsyncSession = Depends(get_db)) -> list[TraceOut]:
    rows = (
        await db.execute(
            select(Trace)
            .options(selectinload(Trace.spans))
            .order_by(Trace.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_trace_out(t) for t in rows]


@router.get("/traces/{trace_id}", response_model=TraceOut)
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)) -> TraceOut:
    result = await db.execute(
        select(Trace).options(selectinload(Trace.spans)).where(Trace.id == trace_id)
    )
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(404, "Trace not found")
    return _trace_out(trace)


def _trace_out(t: Trace) -> TraceOut:
    spans = sorted(t.spans or [], key=lambda s: s.start_time)
    return TraceOut(
        id=t.id,
        agent_id=t.agent_id,
        agent_version_id=t.agent_version_id,
        conversation_id=t.conversation_id,
        status=t.status,
        latency_ms=t.latency_ms,
        total_tokens=t.total_tokens,
        estimated_cost_usd=t.estimated_cost_usd,
        error=t.error,
        created_at=t.created_at,
        spans=[
            TraceSpanOut(
                id=s.id,
                span_type=s.span_type,
                name=s.name,
                latency_ms=s.latency_ms,
                success=s.success,
                metadata_json=s.metadata_json or {},
                start_time=s.start_time,
                end_time=s.end_time,
            )
            for s in spans
        ],
    )


# ---------- Evaluations ----------


@router.post("/evaluations/run", response_model=EvaluationOut)
async def run_evaluation(
    payload: EvaluationRunRequest, db: AsyncSession = Depends(get_db)
) -> EvaluationOut:
    try:
        agent = await agent_service.get_agent(db, payload.agent_id)
        version = await agent_service.resolve_active_version(db, agent)
    except AgentForgeError as exc:
        raise _http_error(exc) from exc

    evaluation = Evaluation(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        agent_version_id=version.id,
        name=payload.name,
        dataset=payload.dataset,
        status="running",
    )
    db.add(evaluation)
    await db.flush()

    runner = EvaluationRunner()
    case_results = []
    for item in payload.dataset:
        example = EvalExample(
            question=item["question"],
            expected_answer=item.get("expected_answer", ""),
            expected_source=item.get("expected_source"),
        )
        chat_resp = await agent_service.chat(
            db, agent.id, ChatRequest(message=example.question)
        )
        case = await runner.run_case(
            example,
            chat_resp.answer,
            citations=chat_resp.citations,
            tool_success=all(t.get("success", True) for t in chat_resp.tool_results)
            if chat_resp.tool_results
            else None,
            latency_ms=chat_resp.latency_ms,
            estimated_cost_usd=chat_resp.estimated_cost.get("estimated_total_cost_usd", 0.0),
        )
        case_results.append(
            {
                "question": case.question,
                "expected_answer": case.expected_answer,
                "actual_answer": case.actual_answer,
                "metrics": case.metrics,
            }
        )

    metrics = runner.aggregate(
        [
            # rebuild lightweight for aggregate
            __import__("app.evaluation.runner", fromlist=["EvalCaseResult"]).EvalCaseResult(
                question=c["question"],
                expected_answer=c["expected_answer"],
                actual_answer=c["actual_answer"],
                metrics=c["metrics"],
            )
            for c in case_results
        ]
    )
    evaluation.results = case_results
    evaluation.metrics = metrics
    evaluation.status = "completed"
    evaluation.completed_at = datetime.utcnow()
    await db.flush()
    return EvaluationOut.model_validate(evaluation)


@router.get("/evaluations", response_model=list[EvaluationOut])
async def list_evaluations(db: AsyncSession = Depends(get_db)) -> list[EvaluationOut]:
    rows = (
        await db.execute(select(Evaluation).order_by(Evaluation.created_at.desc()))
    ).scalars().all()
    return [EvaluationOut.model_validate(e) for e in rows]
