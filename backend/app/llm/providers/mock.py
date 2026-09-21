"""Mock LLM provider for local development without API keys."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, AsyncIterator

from app.llm.base import GenerateResult, LLMProvider, ModelInfo, TokenUsage


class MockProvider(LLMProvider):
    name = "mock"

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> GenerateResult:
        start = time.perf_counter()
        await asyncio.sleep(0.02)
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        system = next((m["content"] for m in messages if m["role"] == "system"), "")

        # Simulate tool-calling hint for calculator
        calc = re.search(r"calculate\s+([0-9+\-*/().\s]+)", user, re.I)
        if calc:
            content = f"TOOL_CALL:calculator:{calc.group(1).strip()}"
        elif "weather" in user.lower():
            city = "San Francisco"
            m = re.search(r"weather\s+(?:in\s+)?([A-Za-z\s]+)", user, re.I)
            if m:
                city = m.group(1).strip()
            content = f"TOOL_CALL:weather:{city}"
        elif any(
            k in user.lower()
            for k in ("document", "according to", "knowledge", "pdf", "cite", "source")
        ) or "retrieved context" in system.lower():
            content = (
                "Based on the retrieved context, here is the answer. "
                "[citation:doc]\n\n"
                f"Regarding your question: {user[:200]}"
            )
            if "Context:" in system or "retrieved" in system.lower():
                # Extract a snippet from context if present
                ctx = system.split("Context:", 1)[-1][:400] if "Context:" in system else ""
                if ctx.strip():
                    content = (
                        f"Based on the knowledge base: {ctx.strip()[:300]}... "
                        f"({user[:100]})"
                    )
        else:
            content = (
                f"[mock:{model}] I processed your request. "
                f"Response to: {user[:300] or 'empty query'}"
            )

        latency = (time.perf_counter() - start) * 1000
        in_tok = max(1, len(str(messages)) // 4)
        out_tok = max(1, len(content) // 4)
        return GenerateResult(
            content=content,
            usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
            model=model,
            provider=self.name,
            latency_ms=latency,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        result = await self.generate(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for word in result.content.split(" "):
            yield word + " "
            await asyncio.sleep(0.005)

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)

    def get_model_info(self, model: str) -> ModelInfo:
        return ModelInfo(provider=self.name, model=model)
