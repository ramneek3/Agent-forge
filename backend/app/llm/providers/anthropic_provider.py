"""Anthropic provider adapter."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.core.exceptions import ProviderError
from app.llm.base import GenerateResult, LLMProvider, ModelInfo, TokenUsage


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_settings().anthropic_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ProviderError("Anthropic API key not configured", provider=self.name)
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _split_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, list[dict[str, str]]]:
        system = ""
        converted: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                role = m["role"] if m["role"] in ("user", "assistant") else "user"
                converted.append({"role": role, "content": m["content"]})
        return system.strip(), converted or [{"role": "user", "content": "Hello"}]

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
        system, converted = self._split_messages(messages)
        try:
            client = self._get_client()
            resp = await client.messages.create(
                model=model,
                system=system or "You are a helpful assistant.",
                messages=converted,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise ProviderError(str(exc), provider=self.name) from exc

        content = ""
        for block in resp.content:
            if hasattr(block, "text"):
                content += block.text
        latency = (time.perf_counter() - start) * 1000
        return GenerateResult(
            content=content,
            usage=TokenUsage(
                input_tokens=getattr(resp.usage, "input_tokens", 0),
                output_tokens=getattr(resp.usage, "output_tokens", 0),
            ),
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
        system, converted = self._split_messages(messages)
        client = self._get_client()
        async with client.messages.stream(
            model=model,
            system=system or "You are a helpful assistant.",
            messages=converted,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)

    def get_model_info(self, model: str) -> ModelInfo:
        return ModelInfo(provider=self.name, model=model)
