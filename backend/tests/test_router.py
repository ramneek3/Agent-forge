"""Model router and cost calculation tests."""

import pytest

from app.core.pricing import estimate_cost, get_pricing
from app.llm.registry import ProviderRegistry
from app.llm.router import ModelRouter


@pytest.mark.asyncio
async def test_manual_routing():
    router = ModelRouter(ProviderRegistry())
    result, decision = await router.generate(
        [{"role": "user", "content": "hello"}],
        strategy="MANUAL",
        provider="mock",
        model="mock-smart",
    )
    assert decision.provider == "mock"
    assert decision.model == "mock-smart"
    assert decision.fallback_used is False
    assert result.content


@pytest.mark.asyncio
async def test_cheapest_routing():
    router = ModelRouter(ProviderRegistry())
    result, decision = await router.generate(
        [{"role": "user", "content": "hello"}],
        strategy="CHEAPEST",
        provider="openai",
        model="gpt-4o",
    )
    assert decision.strategy == "CHEAPEST"
    # cheapest configured is mock:mock-fast or google flash — check it's not premium gpt-4o
    assert decision.model != "gpt-4o"
    assert result.content


@pytest.mark.asyncio
async def test_fastest_routing_uses_configured_latency():
    router = ModelRouter(ProviderRegistry())
    _, decision = await router.generate(
        [{"role": "user", "content": "hello"}],
        strategy="FASTEST",
        provider="openai",
        model="gpt-4o",
    )
    assert decision.strategy == "FASTEST"
    pricing = get_pricing(decision.provider, decision.model)
    assert pricing.estimated_latency_ms <= get_pricing("openai", "gpt-4o").estimated_latency_ms


@pytest.mark.asyncio
async def test_fallback_on_primary_failure():
    router = ModelRouter(ProviderRegistry())
    result, decision = await router.generate(
        [{"role": "user", "content": "hello"}],
        strategy="FALLBACK",
        provider="openai",
        model="gpt-4o",
        fallback_provider="mock",
        fallback_model="mock-fast",
        force_primary_failure=True,
    )
    assert decision.fallback_used is True
    assert decision.provider == "mock"
    assert decision.model == "mock-fast"
    assert len(decision.attempted) == 2
    assert result.content


def test_cost_estimation():
    costs = estimate_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
    assert costs["estimated_input_cost_usd"] == 0.15
    assert costs["estimated_output_cost_usd"] == 0.60
    assert costs["estimated_total_cost_usd"] == 0.75
