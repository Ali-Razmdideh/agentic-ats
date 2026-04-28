"""Token usage + cost accounting.

Prices are USD per 1M tokens, sourced from OpenRouter's catalog (April 2026).
Adjust if you re-route to native Anthropic billing or change models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Prices in USD per 1M tokens. Keys are normalised model IDs.
PRICES: dict[str, tuple[float, float]] = {
    # input, output
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-opus-4.7": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-7": (15.00, 75.00),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    by_agent: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(
        self,
        agent: str,
        model: str,
        in_tok: int,
        out_tok: int,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> None:
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write

        in_price, out_price = PRICES.get(model, (0.0, 0.0))
        # Cache reads are typically ~10% of input price; we approximate.
        cost = (
            in_tok * in_price / 1_000_000
            + out_tok * out_price / 1_000_000
            + cache_read * in_price * 0.1 / 1_000_000
            + cache_write * in_price * 1.25 / 1_000_000
        )
        self.cost_usd += cost

        slot = self.by_agent.setdefault(
            agent, {"input": 0, "output": 0, "cost_usd": 0.0}
        )
        slot["input"] += in_tok
        slot["output"] += out_tok
        slot["cost_usd"] += cost

    def to_dict(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "by_agent": {
                k: {**v, "cost_usd": round(float(v["cost_usd"]), 4)}
                for k, v in self.by_agent.items()
            },
        }


class BudgetExceeded(RuntimeError):
    """Raised when cumulative cost crosses ``--max-cost-usd``."""
