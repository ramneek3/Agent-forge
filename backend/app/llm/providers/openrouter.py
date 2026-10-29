"""OpenRouter provider adapter (OpenAI-compatible API, includes free models)."""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.providers.openai_provider import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    # Free models can queue; fail over to the fallback model instead of hanging the chat
    timeout_seconds = 60.0

    def _default_api_key(self) -> str:
        return get_settings().openrouter_api_key
