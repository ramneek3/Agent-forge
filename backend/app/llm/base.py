"""LLM provider interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class GenerateResult:
    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class ModelInfo:
    provider: str
    model: str
    max_tokens: int = 8192
    supports_tools: bool = True
    supports_streaming: bool = True


class LLMProvider(ABC):
    """Common interface for all LLM providers."""

    name: str

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> GenerateResult:
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def count_tokens(self, text: str, model: str | None = None) -> int:
        ...

    @abstractmethod
    def get_model_info(self, model: str) -> ModelInfo:
        ...
