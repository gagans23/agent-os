"""Tests for the hardware-aware model advisor (deterministic logic + safety)."""

from __future__ import annotations

from agent_os.doctor import (
    Diagnosis,
    diagnose,
    est_size_gb,
    recommend_model,
    render,
    smart_pick,
)


def _diag(**kw) -> Diagnosis:
    base = dict(
        os="Darwin 25", arch="arm64", cpus=18, ram_gb=64.0, apple_silicon=True,
        nvidia_vram_gb=None, ollama_installed=True, ollama_running=True,
        ollama_models=[], budget_gb=44.8, recommended="llama3.1:70b", too_big=[],
    )
    base.update(kw)
    return Diagnosis(**base)


def test_est_size_exact_for_catalog_and_estimated_otherwise() -> None:
    assert est_size_gb("llama3.1:70b") == 42.0          # exact catalog hit
    assert est_size_gb("qwen3:32b") == round(32 * 0.7, 1)  # estimated from "32b"
    assert est_size_gb("gemma4:latest") is None         # no parseable size


def test_smart_pick_uses_recommendation_when_already_present() -> None:
    d = _diag(ollama_models=["llama3.1:70b", "nomic-embed-text:latest"])
    p = smart_pick(d)
    assert p.model == "llama3.1:70b" and p.already_present and p.upgrade is None


def test_smart_pick_prefers_largest_present_model_and_offers_upgrade() -> None:
    # Recommendation (70b) not downloaded, but capable models are present →
    # enable the biggest that fits instantly, offer the 70b as an upgrade.
    d = _diag(ollama_models=["llama3.1:8b", "qwen3:32b", "nomic-embed-text:latest"])
    p = smart_pick(d)
    assert p.model == "qwen3:32b"       # largest present that fits the 44.8 budget
    assert p.already_present is True
    assert p.upgrade == "llama3.1:70b"


def test_smart_pick_skips_models_that_exceed_budget() -> None:
    d = _diag(budget_gb=7.0, ollama_models=["llama3.1:8b", "qwen3:32b"])
    p = smart_pick(d)
    assert p.model == "llama3.1:8b"     # 32b (~22 GB) exceeds a 7 GB budget


def test_smart_pick_falls_back_to_download_when_nothing_present() -> None:
    d = _diag(ollama_models=["nomic-embed-text:latest"])
    p = smart_pick(d)
    assert p.model == "llama3.1:70b" and p.already_present is False


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
