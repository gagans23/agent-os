"""
metering — cost / latency / token accounting (the budget layer).

agent-os already scores every run for **quality** (Ninja Harness) and gates it for
**safety** (risk). Metering adds the third axis production teams care about: **cost**
— so a run is quality- *and* cost- *and* safety-accounted. It also powers optional
budget caps.

Honest by construction:
- **Token counts are estimates** (~4 chars/token) — no tokenizer dependency, no
  hidden call. Good enough for budgeting; labelled "~" everywhere.
- **Prices are approximate** and for local models (Ollama) the cost is **$0**.
  Verify against your provider's current pricing before trusting a number.

Pure standard library; nothing here makes a network call.
"""

from __future__ import annotations

from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Rough token estimate without a tokenizer dependency (~4 chars/token)."""
    return max(0, round(len(text or "") / 4))


# Approximate USD per 1,000 tokens as (input, output). Local backends are free.
# ESTIMATES for budgeting only — not billing. Longest-prefix match wins.
_PRICING: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "echo": (0.0, 0.0),
    "openai": (0.0005, 0.0015),                       # generic default
    "openai:gpt-4o-mini": (0.00015, 0.0006),
    "openai:gpt-4o": (0.0025, 0.01),
    "anthropic": (0.003, 0.015),                      # generic default
    "anthropic:claude-3-5-haiku": (0.0008, 0.004),
    "anthropic:claude-3-5-sonnet": (0.003, 0.015),
}


def price_for(provider_name: str) -> tuple[float, float]:
    name = (provider_name or "").lower()
    best_key = ""
    for key in _PRICING:
        if name.startswith(key) and len(key) > len(best_key):
            best_key = key
    return _PRICING.get(best_key, (0.0, 0.0))


def estimate_cost(provider_name: str, in_tokens: int, out_tokens: int) -> float:
    p_in, p_out = price_for(provider_name)
    return round(in_tokens / 1000 * p_in + out_tokens / 1000 * p_out, 6)


@dataclass
class Meter:
    """Per-job resource use. Cost is computed lazily because it depends on which
    provider actually served the run (which run_job is deliberately agnostic of)."""
    latency_s: float = 0.0
    in_tokens: int = 0
    out_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.in_tokens + self.out_tokens

    def cost(self, provider_name: str) -> float:
        return estimate_cost(provider_name, self.in_tokens, self.out_tokens)

    def line(self, provider_name: str | None = None) -> str:
        """A compact one-liner: `0.42s · ~340 tok · ~$0.0003 (openai:gpt-4o-mini)`."""
        bits = [f"{self.latency_s:.2f}s", f"~{self.total_tokens} tok"]
        if provider_name:
            c = self.cost(provider_name)
            bits.append(f"~${c:.4f} ({provider_name})" if c > 0
                        else f"$0.00 ({provider_name}, local/free)")
        return " · ".join(bits)


def fmt_cost(usd: float) -> str:
    return "$0.00" if usd <= 0 else f"~${usd:.4f}"
