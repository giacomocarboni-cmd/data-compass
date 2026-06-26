"""
Cost and model accounting — Phase 4.

compute_cost(usage, model) → float (GBP)
build_cost_line(usages)    → CostLine
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_compass.config import CACHE_READ_MULTIPLIER, FX_USD_TO_GBP, MODEL_RATES

_MODEL_LABELS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "Haiku",
    "claude-haiku-4-5": "Haiku",
    "claude-sonnet-4-6": "Sonnet",
    "claude-opus-4-8": "Opus",
}


@dataclass
class CostLine:
    """Accounting for one or more LLM calls within a single query."""
    models: list[str] = field(default_factory=list)
    cost_gbp: float = 0.0

    @property
    def label(self) -> str:
        if not self.models:
            return f"No AI used · £{self.cost_gbp:.4f}"
        names = " + ".join(
            _MODEL_LABELS.get(m, m) for m in self.models
        )
        return f"{names} · £{self.cost_gbp:.4f}"


def compute_cost(usage: Any, model: str) -> float:
    """Return the cost in GBP for a single Anthropic API call.

    Cache writes are billed at the same rate as regular input tokens.
    Cache reads are billed at CACHE_READ_MULTIPLIER × the input rate.
    """
    if usage is None:
        return 0.0
    rates = MODEL_RATES.get(model, {})
    if not rates:
        return 0.0

    input_rate = rates["input"]
    output_rate = rates["output"]

    cost_usd = (
        getattr(usage, "input_tokens", 0) / 1_000_000 * input_rate
        + getattr(usage, "output_tokens", 0) / 1_000_000 * output_rate
        + getattr(usage, "cache_creation_input_tokens", 0) / 1_000_000 * input_rate
        + getattr(usage, "cache_read_input_tokens", 0) / 1_000_000 * input_rate * CACHE_READ_MULTIPLIER
    )
    return cost_usd * FX_USD_TO_GBP


def build_cost_line(usages: list[tuple[str, Any]]) -> CostLine:
    """Build a CostLine from a list of (model_id, usage) pairs.

    Pass an empty list for the no-AI path (exact cache hit, etc.).
    """
    if not usages:
        return CostLine()
    models = [model for model, usage in usages if usage is not None]
    total = sum(compute_cost(usage, model) for model, usage in usages)
    return CostLine(models=models, cost_gbp=total)
