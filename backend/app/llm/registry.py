"""Provider registry and factory."""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai_provider import OpenAIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        settings = get_settings()
        self._providers["mock"] = MockProvider()
        if settings.openai_api_key and not settings.llm_mock_mode:
            self._providers["openai"] = OpenAIProvider()
        else:
            # Always register adapters; they fail clearly if key missing unless mock mode
            self._providers["openai"] = (
                MockProvider() if settings.llm_mock_mode else OpenAIProvider()
            )
            if settings.llm_mock_mode:
                # Keep named mock under openai for routing demos when keys absent
                pass
        if settings.anthropic_api_key and not settings.llm_mock_mode:
            self._providers["anthropic"] = AnthropicProvider()
        else:
            self._providers["anthropic"] = (
                MockProvider() if settings.llm_mock_mode else AnthropicProvider()
            )
        if settings.google_api_key and not settings.llm_mock_mode:
            self._providers["google"] = GeminiProvider()
        else:
            self._providers["google"] = (
                MockProvider() if settings.llm_mock_mode else GeminiProvider()
            )

        # When mock mode, wrap so provider name is preserved in results
        if settings.llm_mock_mode:
            for name in ("openai", "anthropic", "google"):
                self._providers[name] = _NamedMock(name)

    def get(self, provider: str) -> LLMProvider:
        if provider not in self._providers:
            raise KeyError(f"Unknown provider: {provider}")
        return self._providers[provider]

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())


class _NamedMock(MockProvider):
    def __init__(self, name: str):
        self.name = name

    async def generate(self, messages, *, model, temperature=0.2, max_tokens=2048, **kwargs):
        result = await super().generate(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
        )
        result.provider = self.name
        return result


_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_provider_registry() -> None:
    global _registry
    _registry = None
