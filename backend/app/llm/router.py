"""Model router with MANUAL, CHEAPEST, FASTEST, FALLBACK strategies."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import ProviderError
from app.core.pricing import get_pricing, list_models
from app.llm.base import GenerateResult
from app.llm.registry import ProviderRegistry, get_provider_registry


@dataclass
class RouteDecision:
    provider: str
    model: str
    strategy: str
    fallback_used: bool = False
    attempted: list[dict[str, Any]] = field(default_factory=list)


class ModelRouter:
    """Selects and invokes LLM providers based on routing strategy."""

    def __init__(self, registry: ProviderRegistry | None = None):
        self.registry = registry or get_provider_registry()

    def select(
        self,
        strategy: str,
        primary_provider: str,
        primary_model: str,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> RouteDecision:
        strategy = strategy.upper()
        if strategy == "MANUAL":
            return RouteDecision(primary_provider, primary_model, strategy)
        if strategy == "CHEAPEST":
            p, m = self._cheapest()
            return RouteDecision(p, m, strategy)
        if strategy == "FASTEST":
            p, m = self._fastest()
            return RouteDecision(p, m, strategy)
        if strategy == "FALLBACK":
            return RouteDecision(
                primary_provider,
                primary_model,
                strategy,
                fallback_used=False,
                attempted=[],
            )
        return RouteDecision(primary_provider, primary_model, "MANUAL")

    def _cheapest(self) -> tuple[str, str]:
        models = list_models()
        models_sorted = sorted(
            models, key=lambda x: x["input_per_1m_usd"] + x["output_per_1m_usd"]
        )
        best = models_sorted[0]
        return best["provider"], best["model"]

    def _fastest(self) -> tuple[str, str]:
        """Uses configured estimated_latency_ms metadata — not live RTT."""
        models = list_models()
        models_sorted = sorted(models, key=lambda x: x["estimated_latency_ms"])
        best = models_sorted[0]
        return best["provider"], best["model"]

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        strategy: str = "MANUAL",
        provider: str = "mock",
        model: str = "mock-smart",
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        force_primary_failure: bool = False,
    ) -> tuple[GenerateResult, RouteDecision]:
        decision = self.select(
            strategy, provider, model, fallback_provider, fallback_model
        )

        if strategy.upper() != "FALLBACK":
            result = await self._call(
                decision.provider, decision.model, messages, temperature, max_tokens
            )
            return result, decision

        # FALLBACK strategy
        primary_p, primary_m = provider, model
        secondary_p = fallback_provider or "mock"
        secondary_m = fallback_model or "mock-fast"
        attempted: list[dict[str, Any]] = []

        try:
            if force_primary_failure:
                raise ProviderError("Forced primary failure for fallback demo", provider=primary_p)
            result = await self._call(
                primary_p, primary_m, messages, temperature, max_tokens
            )
            attempted.append(
                {"provider": primary_p, "model": primary_m, "success": True}
            )
            decision = RouteDecision(
                primary_p, primary_m, "FALLBACK", False, attempted
            )
            return result, decision
        except Exception as primary_exc:
            attempted.append(
                {
                    "provider": primary_p,
                    "model": primary_m,
                    "success": False,
                    "error": str(primary_exc),
                }
            )
            result = await self._call(
                secondary_p, secondary_m, messages, temperature, max_tokens
            )
            attempted.append(
                {"provider": secondary_p, "model": secondary_m, "success": True}
            )
            decision = RouteDecision(
                secondary_p, secondary_m, "FALLBACK", True, attempted
            )
            result.raw["fallback_from"] = f"{primary_p}:{primary_m}"
            return result, decision

    async def _call(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> GenerateResult:
        start = time.perf_counter()
        llm = self.registry.get(provider)
        # For named mocks, ensure model name passes through
        result = await llm.generate(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        if not result.latency_ms:
            result.latency_ms = (time.perf_counter() - start) * 1000
        result.provider = provider
        result.model = model
        # Attach pricing metadata for callers
        pricing = get_pricing(provider, model)
        result.raw["estimated_latency_ms_config"] = pricing.estimated_latency_ms
        return result
