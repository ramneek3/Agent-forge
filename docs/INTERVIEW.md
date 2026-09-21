# AgentForge — Interview Q&A

Answers grounded in what this repo actually implements.

1. **What problem does AgentForge solve?**  
   Production agents need orchestration, retrieval, tools, versioning, guardrails, cost visibility, and evals — not a single chat completion.

2. **Why can't we simply call an LLM API?**  
   No retrieval, no tool contracts, no fallbacks, no traces, no cost attribution, no rollback when prompts regress.

3. **Why do we need an agent runtime?**  
   To coordinate classify → retrieve → reason → tool/MCP → generate → guardrails with shared state.

4. **Why LangGraph?**  
   Explicit graph state, nodes, and conditional edges; bounded iterations; clearer than ad-hoc while-loops.

5. **How does state move through the graph?**  
   `AgentState` TypedDict is passed/updated by each node (`app/agents/graph.py`).

6. **How does RAG work?**  
   Ingest → chunk → embed → store → query embed → cosine top_k with threshold → citations.

7. **Why pgvector?**  
   Postgres-native vector search next to relational data; Docker image `pgvector/pgvector`. Local/tests also store vectors as JSON for SQLite.

8. **How does tool calling work?**  
   Registry of tools with schema + `execute`; graph routes to tools; results return into generation context.

9. **What is MCP?**  
   Model Context Protocol — standard way to expose external tools to agents.

10. **Why is MCP useful?**  
    Reuse external servers (e.g. GitHub) without rewriting integrations per agent.

11. **How does model routing work?**  
    `ModelRouter` strategies: MANUAL, CHEAPEST, FASTEST, FALLBACK using pricing metadata.

12. **How do fallbacks work?**  
    Primary call; on failure (or forced demo failure) call secondary; `fallback_used` recorded.

13. **How are tokens calculated?**  
    Provider usage when available; otherwise approximate (`len/4` or tiktoken for OpenAI).

14. **How is cost calculated?**  
    `estimate_cost()` from centralized `MODEL_PRICING` (USD per 1M tokens) — labeled estimates.

15. **How do we trace an agent execution?**  
    `Tracer` builds spans persisted as `Trace` / `TraceSpan`.

16. **How do we detect failures?**  
    Span success flags, Prometheus `agent_errors_total`, guardrail failures, tool error counters.

17. **How do guardrails work?**  
    Input (length/injection/blocked) before graph; output (empty/unsafe/grounding) after generate.

18. **How do we evaluate an agent?**  
    Dataset run through live chat; heuristic metrics + clearly labeled LLM-as-judge stand-in.

19. **How do we version agents?**  
    Immutable `AgentVersion` rows with status enum.

20. **How do we roll back?**  
    Point `production_version_id` at a prior version; archive current — no overwrite.

21. **How would this scale to thousands of requests?**  
    Stateless API replicas, connection-pooled Postgres, async IO, queue long jobs, cache embeddings.

22. **How would you isolate tenants?**  
    `org_id` on all rows + RLS / separate schemas; per-tenant API keys; no shared traces.

23. **How would you secure tool execution?**  
    Allowlists, schema validation, no shell/eval (calculator is AST-safe), sandboxed workers for risky tools.

24. **How would you prevent prompt injection?**  
    Pattern checks + output grounding + tool allowlists; never execute raw model text as code.

25. **How would you reduce LLM cost?**  
    CHEAPEST routing, smaller models, RAG to shrink prompts, cache frequent answers, mock for tests.

26. **How would you reduce latency?**  
    FASTEST routing metadata, parallel retrieve where safe, smaller models, connection reuse, edge caching of static KB.
