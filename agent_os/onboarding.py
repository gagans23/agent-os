"""
onboarding — the guided "click a button" setup flow (Module 3).

Turns the five scattered steps a new user faces (install Python, install Ollama,
pull a model, set an env var, verify it works) into one guided flow:

    agent-os setup            # explain every step + the exact commands (safe; no changes)
    agent-os setup --run      # also pull the model + persist the choice for you

Principles, unchanged:

  - **Default-deny / nothing privileged without your OK.** Plain `setup` only
    *reads* (hardware, Ollama status) and *prints* commands. It changes nothing.
    Only `--run` performs actions, and even then it never installs system
    software silently — installing Ollama is always shown as a command for you to
    run, because auto-installing system packages for someone is exactly the line
    we don't cross. What `--run` does do is the safe, idempotent, no-sudo part:
    pull the model and persist your provider choice.
  - **Never faked.** Detection and the model pull are real (they shell out to the
    `ollama` already on your machine); nothing is mocked or phoned home.
  - **Local-first.** The chosen provider is saved to a small JSON config file so
    it survives restarts without you editing a shell profile.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from agent_os import doctor
from agent_os.providers import OllamaProvider, set_configured_provider

Writer = Callable[[str], None]
Shell = Callable[[list[str], Writer], int]


@dataclass
class SetupResult:
    recommended: str
    provider_spec: str
    ollama_installed: bool
    ollama_running: bool
    model_present: bool
    executed: bool
    persisted_to: str | None = None
    verified: bool = False
    steps: list[str] = field(default_factory=list)


def install_hint(system: str | None = None) -> str:
    """The exact, platform-correct way to install Ollama (free, local)."""
    system = system or platform.system()
    if system == "Darwin":
        return ("Install Ollama (free):  https://ollama.com/download\n"
                "    …or with Homebrew:   brew install ollama")
    if system == "Linux":
        return "Install Ollama (free):  curl -fsSL https://ollama.com/install.sh | sh"
    if system == "Windows":
        return "Install Ollama (free):  https://ollama.com/download  (run the installer)"
    return "Install Ollama (free):  https://ollama.com/download"


def _default_shell(cmd: list[str], writer: Writer) -> int:
    """Run a command, streaming its output line-by-line. Real subprocess."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,  # noqa: S603
                                stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        writer(f"    (command not found: {cmd[0]})")
        return 127
    assert proc.stdout is not None
    for line in proc.stdout:
        writer("    " + line.rstrip())
    return proc.wait()


def guidance(diag: doctor.Diagnosis | None = None, model: str | None = None) -> str:
    """Pure, read-only setup instructions (no execution). Used by the CLI's dry
    run, the `/setup` command, and the web UI's empty state."""
    d = diag or doctor.diagnose()
    rec = model or d.recommended or "llama3.2:3b"
    spec = f"ollama:{rec}"
    has_model = rec in d.ollama_models
    lines = ["🚀 agent-os setup — get to a working local model in a few steps", ""]
    # Step 1 — Ollama
    if not d.ollama_installed:
        lines += ["1. " + install_hint().replace("\n", "\n   ")]
    elif not d.ollama_running:
        lines += ["1. Start Ollama:  ollama serve   (or open the Ollama app)"]
    else:
        lines += ["1. Ollama is installed and running ✅"]
    # Step 2 — model
    if has_model:
        lines += [f"2. Model {rec} is already pulled ✅"]
    else:
        lines += [f"2. Pull your recommended model:  ollama pull {rec}",
                  f"   (optional, better Brain search:  ollama pull {d.embed_recommended})"]
    # Step 3 — enable
    lines += ["3. Enable it:  agent-os setup --run        (pulls + remembers your choice)",
              f"   …or by hand:  export AGENT_OS_PROVIDER={spec}"]
    # Step 4 — use
    lines += ["4. Use it:  agent-os ui     (or:  agent-os cmd \"/ask ...\")", ""]
    lines += [f"Recommended for this machine: {spec}",
              "Tip: agent-os already works with no model (deterministic demo mode) — "
              "a model just makes /ask and /run smart."]
    return "\n".join(lines)


def run_setup(*, execute: bool = False, model: str | None = None,
              writer: Writer = print, shell: Shell | None = None,
              diag: doctor.Diagnosis | None = None,
              persist: bool = True) -> SetupResult:
    """Run the guided setup.

    execute=False (default): explain + print commands, change nothing.
    execute=True  (`--run`): pull the model (if Ollama is ready) and persist the
                  provider choice. Installing Ollama itself is always left to you.
    """
    shell = shell or _default_shell
    d = diag or doctor.diagnose()
    rec = model or d.recommended or "llama3.2:3b"
    spec = f"ollama:{rec}"
    res = SetupResult(
        recommended=rec, provider_spec=spec,
        ollama_installed=d.ollama_installed, ollama_running=d.ollama_running,
        model_present=rec in d.ollama_models, executed=execute,
    )

    writer("🚀 agent-os setup")
    writer(f"   Machine : {d.os} · {d.arch} · {d.ram_gb or '?'} GB RAM")
    writer(f"   Pick    : {spec}  ({next((n for t, _g, n in doctor.CATALOG if t == rec), '')})")
    writer("")

    # Step 1 — Ollama present?
    if not d.ollama_installed:
        writer("① Ollama is not installed. It's free and runs models locally:")
        for ln in install_hint().splitlines():
            writer("   " + ln)
        res.steps.append("ollama-install-needed")
        writer("   → Re-run `agent-os setup --run` after installing it.")
    elif not d.ollama_running:
        writer("① Ollama is installed but not running. Start it:")
        writer("   ollama serve     (or open the Ollama app)")
        res.steps.append("ollama-start-needed")
    else:
        writer("① Ollama is installed and running ✅")
        res.steps.append("ollama-ready")

    # Step 2 — model present / pull
    if res.model_present:
        writer(f"② Model {rec} is already available ✅")
        res.steps.append("model-present")
    elif execute and d.ollama_installed and d.ollama_running:
        writer(f"② Pulling {rec} (this can take a few minutes the first time)…")
        code = shell(["ollama", "pull", rec], writer)
        res.model_present = code == 0
        res.steps.append("model-pulled" if code == 0 else "model-pull-failed")
        if code == 0:
            writer(f"   pulling embeddings model {d.embed_recommended} (optional)…")
            shell(["ollama", "pull", d.embed_recommended], writer)
    else:
        writer(f"② Pull the model:  ollama pull {rec}")
        if not execute:
            writer("   (run `agent-os setup --run` to do this for you)")
        res.steps.append("model-pull-needed")

    # Step 3 — persist the provider choice
    if execute and persist:
        path = set_configured_provider(spec)
        res.persisted_to = str(path)
        writer(f"③ Saved your choice: {spec}")
        writer(f"   (remembered in {path}; AGENT_OS_PROVIDER still overrides it)")
        res.steps.append("persisted")
    else:
        writer(f"③ Enable it:  export AGENT_OS_PROVIDER={spec}")
        writer("   (or `agent-os setup --run` to remember it for you)")

    # Step 4 — verify
    if execute and res.model_present and d.ollama_running:
        writer("④ Verifying with a tiny prompt…")
        try:
            out = OllamaProvider(rec).complete("Reply with the single word: ready")
            res.verified = bool(out)
            writer(f"   model says: {out[:80] or '(empty)'}")
            res.steps.append("verified")
        except Exception as exc:  # noqa: BLE001 - verification must not crash setup
            writer(f"   couldn't verify yet ({type(exc).__name__}): {exc}")
            res.steps.append("verify-failed")

    writer("")
    if res.verified:
        writer("✅ You're set. Try:  agent-os ui     (or:  agent-os cmd \"/ask ...\")")
    elif execute and not d.ollama_installed:
        writer("➡️  Install Ollama (above), then re-run:  agent-os setup --run")
    else:
        writer("➡️  Next:  agent-os ui     — works now in demo mode; smart once the model is ready.")
    return res
