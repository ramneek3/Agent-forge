"""API endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_lifecycle_and_chat(client):
    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "demo-agent",
            "description": "Demo",
            "system_prompt": "You are AgentForge demo agent.",
            "model_provider": "mock",
            "model": "mock-smart",
            "routing_strategy": "MANUAL",
            "tools": ["calculator", "weather"],
            "rag_config": {"enabled": True, "top_k": 5, "similarity_threshold": 0.01},
            "mcp_config": {"enabled": True, "server_name": "github"},
        },
    )
    assert create.status_code == 200, create.text
    agent = create.json()
    agent_id = agent["id"]
    version_id = agent["current_version"]["id"]

    # promote draft -> staging -> production
    p1 = await client.post(
        f"/api/v1/agents/{agent_id}/versions/{version_id}/promote",
        json={"target_status": "staging"},
    )
    assert p1.status_code == 200
    p2 = await client.post(
        f"/api/v1/agents/{agent_id}/versions/{version_id}/promote",
        json={"target_status": "production"},
    )
    assert p2.status_code == 200

    # ingest knowledge
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("kb.txt", b"AgentForge uses LangGraph for agent orchestration and pgvector for RAG.", "text/plain")},
    )
    assert upload.status_code == 200

    chat = await client.post(
        f"/api/v1/agents/{agent_id}/chat",
        json={"message": "Based on the knowledge base, what does AgentForge use for orchestration?"},
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["trace_id"]
    assert "token_usage" in body
    assert "estimated_cost" in body
    assert body["answer"]

    tool_chat = await client.post(
        f"/api/v1/agents/{agent_id}/chat",
        json={"message": "Please calculate 21 * 2"},
    )
    assert tool_chat.status_code == 200
    assert tool_chat.json()["tool_results"]

    traces = await client.get("/api/v1/traces")
    assert traces.status_code == 200
    assert len(traces.json()) >= 1

    models = await client.get("/api/v1/models")
    assert models.status_code == 200
    assert len(models.json()) >= 1

    tools = await client.get("/api/v1/tools")
    assert tools.status_code == 200

    mcp = await client.get("/api/v1/mcp/servers")
    assert mcp.status_code == 200


@pytest.mark.asyncio
async def test_fallback_chat(client):
    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "fallback-agent",
            "routing_strategy": "FALLBACK",
            "model_provider": "openai",
            "model": "gpt-4o",
            "fallback_provider": "mock",
            "fallback_model": "mock-fast",
            "tools": [],
            "rag_config": {"enabled": False},
            "mcp_config": {"enabled": False},
        },
    )
    agent = create.json()
    agent_id = agent["id"]
    version_id = agent["current_version"]["id"]
    await client.post(
        f"/api/v1/agents/{agent_id}/versions/{version_id}/promote",
        json={"target_status": "staging"},
    )
    await client.post(
        f"/api/v1/agents/{agent_id}/versions/{version_id}/promote",
        json={"target_status": "production"},
    )
    chat = await client.post(
        f"/api/v1/agents/{agent_id}/chat",
        json={"message": "Hello", "force_primary_failure": True},
    )
    assert chat.status_code == 200
    assert chat.json()["fallback_used"] is True
    assert chat.json()["provider"] == "mock"
