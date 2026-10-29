"""Demo data for hosted deployments whose database resets on restart."""

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models import Agent, RoutingStrategy, VersionStatus
from app.rag.service import get_rag_service
from app.schemas import AgentCreate
from app.services.agents import AgentService

logger = get_logger()

DEMO_KNOWLEDGE = """AgentForge is a production AI agent platform.
It uses LangGraph for agent orchestration, PostgreSQL with pgvector for RAG,
MCP for external tool servers, and Prometheus for observability.
Model routing supports MANUAL, CHEAPEST, FASTEST, and FALLBACK strategies.
Every agent is versioned: versions move from draft to staging to production and can be rolled back.
Guardrails check prompt length, blocked patterns and grounding before a response is returned.
Each run records a trace with latency, token usage and estimated cost per step.
"""


async def seed_demo_data() -> None:
    """Create one production agent and one knowledge document if the database is empty."""
    async with AsyncSessionLocal() as db:
        if await db.scalar(select(func.count()).select_from(Agent)):
            return
        service = AgentService()
        agent = await service.create_agent(
            db,
            AgentCreate(
                name="demo-support",
                description="Demo support agent: answers from the knowledge base and uses tools",
                system_prompt=(
                    "You are AgentForge support. Answer from the knowledge base with citations "
                    "and use tools when helpful."
                ),
                model_provider="google",
                model="gemini-2.5-flash",
                routing_strategy=RoutingStrategy.FALLBACK,
                fallback_provider="mock",
                fallback_model="mock-fast",
                # Hash embeddings (no model on the free tier) score relevant chunks ~0.1-0.2
                rag_config={"enabled": True, "top_k": 5, "similarity_threshold": 0.05},
            ),
        )
        version = (await service.get_versions(db, agent.id))[0]
        for target in (VersionStatus.staging, VersionStatus.production):
            await service.promote_version(db, agent.id, version.id, target, "demo seed")
        await get_rag_service().ingest_text(db, "agentforge-overview.txt", DEMO_KNOWLEDGE)
        await db.commit()
        logger.info("demo_data_seeded", agent_id=agent.id)
