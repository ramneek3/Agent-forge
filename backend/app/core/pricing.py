"""Centralized model pricing configuration (USD per 1M tokens). Estimates only."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_per_1m: float
    output_per_1m: float
    estimated_latency_ms: int  # configured metadata, not live measurement
    tier: str  # cheap | balanced | premium


# Single source of truth for cost estimates. Update here only.
MODEL_PRICING: dict[str, ModelPricing] = {
    "openai:gpt-4o-mini": ModelPricing(
        "openai", "gpt-4o-mini", 0.15, 0.60, 400, "cheap"
    ),
    "openai:gpt-4o": ModelPricing("openai", "gpt-4o", 2.50, 10.00, 800, "premium"),
    "anthropic:claude-3-5-haiku-20241022": ModelPricing(
        "anthropic", "claude-3-5-haiku-20241022", 0.80, 4.00, 500, "cheap"
    ),
    "anthropic:claude-3-5-sonnet-20241022": ModelPricing(
        "anthropic", "claude-3-5-sonnet-20241022", 3.00, 15.00, 900, "premium"
    ),
    "google:gemini-2.5-flash": ModelPricing(
        "google", "gemini-2.5-flash", 0.30, 2.50, 350, "cheap"
    ),
    "google:gemini-2.5-pro": ModelPricing(
        "google", "gemini-2.5-pro", 1.25, 10.00, 850, "premium"
    ),
    "mock:mock-fast": ModelPricing("mock", "mock-fast", 0.01, 0.02, 50, "cheap"),
    "mock:mock-smart": ModelPricing("mock", "mock-smart", 0.05, 0.10, 120, "balanced"),
}


def pricing_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def get_pricing(provider: str, model: str) -> ModelPricing:
    key = pricing_key(provider, model)
    if key in MODEL_PRICING:
        return MODEL_PRICING[key]
    # Unknown models: conservative estimate
    return ModelPricing(provider, model, 1.0, 3.0, 1000, "balanced")


def estimate_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> dict[str, float]:
    """Return estimated costs in USD. Always labeled as estimates by callers."""
    p = get_pricing(provider, model)
    input_cost = (input_tokens / 1_000_000) * p.input_per_1m
    output_cost = (output_tokens / 1_000_000) * p.output_per_1m
    return {
        "estimated_input_cost_usd": round(input_cost, 8),
        "estimated_output_cost_usd": round(output_cost, 8),
        "estimated_total_cost_usd": round(input_cost + output_cost, 8),
    }


def list_models() -> list[dict]:
    return [
        {
            "provider": p.provider,
            "model": p.model,
            "input_per_1m_usd": p.input_per_1m,
            "output_per_1m_usd": p.output_per_1m,
            "estimated_latency_ms": p.estimated_latency_ms,
            "tier": p.tier,
            "key": pricing_key(p.provider, p.model),
        }
        for p in MODEL_PRICING.values()
    ]
