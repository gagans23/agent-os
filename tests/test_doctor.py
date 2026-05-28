"""Tests for the hardware-aware model advisor (deterministic logic + safety)."""

from __future__ import annotations

from agent_os.doctor import (
    Diagnosis,
    diagnose,
    recommend_model,
    render,
)


def test_recommend_scales_with_budget() -> None:
    assert recommend_model(2.5)[0] == "llama3.2:1b"     # only the tiny one fits
    assert recommend_model(4.0)[0] == "llama3.2:3b"
    assert recommend_model(7.0)[0] == "llama3.1:8b"
    assert recommend_model(48.0)[0] == "llama3.1:70b"   # everything fits → biggest


def test_recommend_unknown_budget_is_safe_default() -> None:
    rec, too_big = recommend_model(None)
    assert rec == "llama3.2:3b" and too_big == []


def test_recommend_reports_too_big() -> None:
    _rec, too_big = recommend_model(6.5)
    assert "llama3.1:70b" in too_big and "qwen2.5:32b" in too_big


def test_diagnose_never_crashes_and_has_fields() -> None:
    d = diagnose()
    assert isinstance(d, Diagnosis)
    assert d.os and d.arch and d.recommended


def test_render_includes_recommendation_and_export() -> None:
    d = Diagnosis(
        os="Darwin 23", arch="arm64", cpus=8, ram_gb=16.0, apple_silicon=True,
        nvidia_vram_gb=None, ollama_installed=True, ollama_running=True,
        ollama_models=["llama3.1:8b"], budget_gb=11.2, recommended="llama3.1:8b",
        too_big=["llama3.1:70b"],
    )
    out = render(d)
    assert "Recommended model: llama3.1:8b" in out
    assert "AGENT_OS_PROVIDER=ollama:llama3.1:8b" in out
    assert "Apple Silicon" in out
    assert "llama3.1:70b" in out            # listed as too big


def test_render_guides_install_when_ollama_missing() -> None:
    d = Diagnosis(
        os="Linux", arch="x86_64", cpus=4, ram_gb=8.0, apple_silicon=False,
        nvidia_vram_gb=None, ollama_installed=False, ollama_running=False,
        budget_gb=4.8, recommended="llama3.2:3b",
    )
    out = render(d)
    assert "ollama.com" in out and "ollama pull llama3.2:3b" in out
