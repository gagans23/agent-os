"""Tests for the guided 'click a button' setup flow (onboarding.py).

Everything is exercised offline: hardware detection is stubbed via a fake
Diagnosis, and the model pull is a fake shell that records commands instead of
shelling out to a real `ollama`. The config file is isolated with AGENT_OS_HOME.
Nothing here touches the network or installs software.
"""

from __future__ import annotations

from agent_os import doctor, onboarding, providers


def _diag(*, installed=True, running=True, models=None, recommended="llama3.2:3b"):
    return doctor.Diagnosis(
        os="Darwin", arch="arm64", cpus=8, ram_gb=16.0, apple_silicon=True,
        nvidia_vram_gb=None, ollama_installed=installed, ollama_running=running,
        ollama_models=models or [], recommended=recommended,
    )


def _capture_writer():
    lines: list[str] = []
    return lines, lines.append


# --- install_hint -----------------------------------------------------------

def test_install_hint_is_platform_specific() -> None:
    assert "brew install ollama" in onboarding.install_hint("Darwin")
    assert "install.sh" in onboarding.install_hint("Linux")
    assert "installer" in onboarding.install_hint("Windows")
    assert "ollama.com/download" in onboarding.install_hint("Plan9")  # fallback


# --- guidance (pure, read-only) ---------------------------------------------

def test_guidance_is_read_only_and_mentions_demo_mode() -> None:
    text = onboarding.guidance(diag=_diag(installed=False), model="llama3.2:3b")
    assert "ollama pull llama3.2:3b" in text
    assert "demo mode" in text
    assert "ollama:llama3.2:3b" in text


def test_guidance_acknowledges_ready_model() -> None:
    text = onboarding.guidance(diag=_diag(models=["llama3.2:3b"]), model="llama3.2:3b")
    assert "already pulled" in text


# --- run_setup dry run (changes nothing) ------------------------------------

def test_dry_run_changes_nothing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
    calls: list[list[str]] = []

    def fake_shell(cmd, writer):
        calls.append(cmd)
        return 0

    lines, writer = _capture_writer()
    res = onboarding.run_setup(execute=False, diag=_diag(models=[]),
                               writer=writer, shell=fake_shell)
    assert res.executed is False
    assert calls == []                                   # no pull happened
    assert res.persisted_to is None
    assert not providers.config_path().exists()          # nothing persisted
    assert any("setup --run" in ln for ln in lines)      # tells you how to do it


# --- run_setup --run (pulls + persists + verifies) --------------------------

def test_run_pulls_persists_and_verifies(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_OS_PROVIDER", raising=False)
    pulled: list[list[str]] = []

    def fake_shell(cmd, writer):
        pulled.append(cmd)
        return 0

    # Stub the verification call so no network is touched.
    monkeypatch.setattr(onboarding.OllamaProvider, "complete",
                        lambda self, prompt, **k: "ready")

    lines, writer = _capture_writer()
    res = onboarding.run_setup(execute=True, model="llama3.2:3b",
                               diag=_diag(models=[]), writer=writer, shell=fake_shell)

    assert ["ollama", "pull", "llama3.2:3b"] in pulled
    assert res.model_present is True
    assert res.verified is True
    # Persisted the choice to the isolated config file.
    assert res.persisted_to is not None
    assert providers.configured_provider_spec() == "ollama:llama3.2:3b"


def test_run_never_installs_ollama_when_absent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
    calls: list[list[str]] = []

    def fake_shell(cmd, writer):
        calls.append(cmd)
        return 0

    lines, writer = _capture_writer()
    res = onboarding.run_setup(execute=True, diag=_diag(installed=False, running=False),
                               writer=writer, shell=fake_shell)
    # The binary install is never run for the user — only printed as a command.
    assert calls == []
    assert "ollama-install-needed" in res.steps
    assert any("Install Ollama" in ln for ln in lines)


def test_run_persists_even_if_ollama_not_running(monkeypatch, tmp_path) -> None:
    # We can still remember the user's choice; the pull just waits until Ollama runs.
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_OS_PROVIDER", raising=False)
    lines, writer = _capture_writer()
    res = onboarding.run_setup(execute=True, diag=_diag(running=False),
                               writer=writer, shell=lambda c, w: 0)
    assert res.persisted_to is not None
    assert res.verified is False                          # can't verify without Ollama up


def test_run_pull_failure_is_reported(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))

    def failing_shell(cmd, writer):
        return 1

    lines, writer = _capture_writer()
    res = onboarding.run_setup(execute=True, diag=_diag(models=[]),
                               writer=writer, shell=failing_shell)
    assert res.model_present is False
    assert "model-pull-failed" in res.steps
    assert res.verified is False
