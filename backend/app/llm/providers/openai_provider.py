"""OpenAI provider adapter."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.core.exceptions import ProviderError
from app.llm.base import GenerateResult, LLMProvider, ModelInfo, TokenUsage


class OpenAIProvider(LLMProvider):
    name = "openai"
    base_url: str | None = None
    timeout_seconds: float = 600.0

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or self._default_api_key()
        self._client = None

    def _default_api_key(self) -> str:
        return get_settings().openai_api_key

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ProviderError(f"{self.name} API key not configured", provider=self.name)
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_seconds
            )
        return self._client

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
        try:
            client = self._get_client()
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise ProviderError(str(exc), provider=self.name) from exc

        choice = resp.choices[0].message.content or ""
        usage = resp.usage
        latency = (time.perf_counter() - start) * 1000
        return GenerateResult(
            content=choice,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else self.count_tokens(str(messages)),
                output_tokens=usage.completion_tokens if usage else self.count_tokens(choice),
            ),
            model=model,
            provider=self.name,
            latency_ms=latency,
            raw={"id": getattr(resp, "id", None)},
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
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def count_tokens(self, text: str, model: str | None = None) -> int:
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def get_model_info(self, model: str) -> ModelInfo:
        return ModelInfo(provider=self.name, model=model)
