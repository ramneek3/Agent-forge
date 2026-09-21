"""Google Gemini provider adapter."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.core.exceptions import ProviderError
from app.llm.base import GenerateResult, LLMProvider, ModelInfo, TokenUsage


class GeminiProvider(LLMProvider):
    name = "google"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_settings().google_api_key
        self._configured = False

    def _ensure(self) -> None:
        if not self._configured:
            if not self.api_key:
                raise ProviderError("Google API key not configured", provider=self.name)
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._configured = True

    def _to_prompt(self, messages: list[dict[str, str]]) -> str:
        parts = []
        for m in messages:
            parts.append(f"{m['role'].upper()}: {m['content']}")
        return "\n\n".join(parts)

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
        self._ensure()
        import google.generativeai as genai

        try:
            gm = genai.GenerativeModel(model)
            prompt = self._to_prompt(messages)
            # google SDK is sync — run in thread
            resp = await asyncio.to_thread(
                gm.generate_content,
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            content = resp.text or ""
        except Exception as exc:
            raise ProviderError(str(exc), provider=self.name) from exc

        latency = (time.perf_counter() - start) * 1000
        in_tok = self.count_tokens(prompt)
        out_tok = self.count_tokens(content)
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
            await asyncio.sleep(0.01)

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)

    def get_model_info(self, model: str) -> ModelInfo:
        return ModelInfo(provider=self.name, model=model)
