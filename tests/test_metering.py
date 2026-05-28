"""Tests for the metering / budget layer (deterministic, offline)."""

from __future__ import annotations

from agent_os.metering import (
    Meter,
    estimate_cost,
    estimate_tokens,
    fmt_cost,
    price_for,
)


def test_estimate_tokens_roughly_chars_over_4() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_local_models_are_free() -> None:
    assert price_for("ollama:llama3.1:8b") == (0.0, 0.0)
    assert estimate_cost("ollama:llama3", 10_000, 10_000) == 0.0
    assert estimate_cost("echo", 5000, 5000) == 0.0


def test_price_longest_prefix_wins() -> None:
    # The specific gpt-4o-mini price beats the generic "openai" default.
    assert price_for("openai:gpt-4o-mini") == (0.00015, 0.0006)
    assert price_for("openai:something-else") == (0.0005, 0.0015)  # generic default


def test_estimate_cost_paid_provider() -> None:
    # 1000 in + 1000 out on gpt-4o-mini = 0.00015 + 0.0006
    assert estimate_cost("openai:gpt-4o-mini", 1000, 1000) == round(0.00015 + 0.0006, 6)


def test_unknown_provider_defaults_to_zero() -> None:
    assert estimate_cost("mystery:model", 1000, 1000) == 0.0


def test_meter_line_local_vs_paid() -> None:
    m = Meter(latency_s=0.42, in_tokens=200, out_tokens=140)
    assert m.total_tokens == 340
    local = m.line("ollama:llama3")
    assert "0.42s" in local and "~340 tok" in local and "local/free" in local
    paid = m.line("openai:gpt-4o-mini")
    assert "~$" in paid and "openai:gpt-4o-mini" in paid


def test_fmt_cost() -> None:
    assert fmt_cost(0) == "$0.00"
    assert fmt_cost(0.0012).startswith("~$")
