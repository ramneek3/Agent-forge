#!/usr/bin/env bash
# Seed a demo agent + knowledge document for local demos.
set -euo pipefail
API="${API:-http://localhost:8000/api/v1}"

echo "Creating demo agent..."
AGENT=$(curl -s -X POST "$API/agents" -H 'Content-Type: application/json' -d '{
  "name": "demo-support",
  "description": "Demo production agent for AgentForge walkthrough",
  "system_prompt": "You are AgentForge support. Use knowledge base citations and tools when helpful.",
  "model_provider": "mock",
  "model": "mock-smart",
  "routing_strategy": "FALLBACK",
  "fallback_provider": "mock",
  "fallback_model": "mock-fast",
  "tools": ["calculator", "weather", "web_search", "database_query"],
  "mcp_config": {"enabled": true, "server_name": "github"},
  "rag_config": {"enabled": true, "top_k": 5, "similarity_threshold": 0.15, "always_retrieve": false},
  "guardrail_config": {"require_grounding": false, "blocked_patterns": []}
}')
AGENT_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$AGENT")
VERSION_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['current_version']['id'])" <<<"$AGENT")

echo "Promoting to production..."
curl -s -X POST "$API/agents/$AGENT_ID/versions/$VERSION_ID/promote" \
  -H 'Content-Type: application/json' -d '{"target_status":"staging"}' >/dev/null
curl -s -X POST "$API/agents/$AGENT_ID/versions/$VERSION_ID/promote" \
  -H 'Content-Type: application/json' -d '{"target_status":"production"}' >/dev/null

echo "Uploading knowledge document..."
echo "AgentForge is a production AI agent platform.
It uses LangGraph for agent orchestration, PostgreSQL with pgvector for RAG,
MCP for external tool servers, and Prometheus for observability.
Model routing supports MANUAL, CHEAPEST, FASTEST, and FALLBACK strategies.
" > /tmp/agentforge-kb.txt
curl -s -X POST "$API/documents" -F "file=@/tmp/agentforge-kb.txt;type=text/plain" >/dev/null

echo "Demo agent id: $AGENT_ID"
echo "Try playground chat: Based on the knowledge base, what does AgentForge use for orchestration?"
