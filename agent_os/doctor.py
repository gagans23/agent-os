"""
doctor — hardware-aware model advisor.

Answers the #1 setup question for a non-technical user: *"which model can my
machine actually run?"* It detects your RAM / Apple-Silicon / NVIDIA VRAM and the
Ollama install, then recommends the largest local model that comfortably fits —
and prints the exact one-liner to enable it.

Local-first and dependency-light: detection uses the standard library and shells
out to tools already on your machine (`sysctl`, `/proc/meminfo`, `nvidia-smi`,
`ollama`). Nothing is installed or sent anywhere; if something can't be detected,
we say "unknown" rather than guess.

    agent-os doctor          # report + a recommended model + the export line
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# (Ollama tag, approx RAM/VRAM needed for a Q4_K_M quant, one-line note)
CATALOG: list[tuple[str, float, str]] = [
    ("llama3.2:1b", 2.0, "tiny, fast, runs almost anywhere"),
    ("llama3.2:3b", 3.5, "small + capable; good low-RAM default"),
    ("qwen2.5:7b", 6.0, "strong general 7B"),
    ("llama3.1:8b", 6.5, "well-rounded 8B"),
    ("gemma2:9b", 8.0, "capable 9B"),
    ("qwen2.5:14b", 11.0, "stronger reasoning"),
    ("qwen2.5:32b", 22.0, "high quality, needs a big GPU/Mac"),
    ("llama3.1:70b", 42.0, "frontier-ish local; workstation-class"),
]
EMBED_MODEL = "nomic-embed-text"  # small embedder for the Brain's semantic search


@dataclass
class Diagnosis:
    os: str
    arch: str
    cpus: int | None
    ram_gb: float | None
    apple_silicon: bool
    nvidia_vram_gb: float | None
    ollama_installed: bool
    ollama_running: bool
    ollama_models: list[str] = field(default_factory=list)
    budget_gb: float | None = None
    recommended: str | None = None
    embed_recommended: str = EMBED_MODEL
    too_big: list[str] = field(default_factory=list)


def _run(cmd: list[str], timeout: float = 4.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 - detection must never crash
        return ""


def total_ram_gb() -> float | None:
    system = platform.system()
    try:
        if system == "Darwin":
            out = _run(["sysctl", "-n", "hw.memsize"])
            return round(int(out.strip()) / 2**30, 1) if out.strip() else None
        if system == "Linux":
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 2**20, 1)  # kB → GiB
        if system == "Windows":
            out = _run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"])
            nums = [int(s) for s in out.split() if s.isdigit()]
            if nums:
                return round(nums[0] / 2**30, 1)
    except Exception:  # noqa: BLE001
        return None
    return None


def nvidia_vram_gb() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    out = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
    vals = [float(x) for x in out.replace(",", " ").split() if x.replace(".", "", 1).isdigit()]
    return round(max(vals) / 1024, 1) if vals else None  # MiB → GiB


def ollama_status() -> tuple[bool, bool, list[str]]:
    installed = shutil.which("ollama") is not None
    running, models = False, []
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:  # noqa: S310
            data = json.loads(r.read())
            running = True
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:  # noqa: BLE001 - Ollama may not be running; that's fine
        pass
    return installed, running, models


def _budget_gb(ram_gb: float | None, apple_silicon: bool,
               vram_gb: float | None) -> float | None:
    if vram_gb:
        return vram_gb                       # dedicated GPU → VRAM-bound
    if ram_gb is None:
        return None
    # Apple unified memory shares with the OS; CPU-only is RAM-bound + slower.
    return round(ram_gb * (0.7 if apple_silicon else 0.6), 1)


def recommend_model(budget_gb: float | None) -> tuple[str, list[str]]:
    """Return (recommended_tag, too_big_tags) for a memory budget in GB."""
    if budget_gb is None:
        return "llama3.2:3b", []
    fits = [m for m in CATALOG if m[1] <= budget_gb]
    too_big = [m[0] for m in CATALOG if m[1] > budget_gb]
    return (fits[-1][0] if fits else "llama3.2:1b"), too_big


def _params_b(tag: str) -> float | None:
    """Best-effort parameter count (in billions) parsed from an Ollama tag."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag.lower())
    return float(m.group(1)) if m else None


def est_size_gb(tag: str) -> float | None:
    """Rough memory footprint for a model tag (Q4-ish). Exact for CATALOG tags,
    estimated from the parameter count otherwise; None if it can't be guessed."""
    for t, g, _n in CATALOG:
        if t == tag:
            return g
    p = _params_b(tag)
    return round(p * 0.7, 1) if p else None


@dataclass
class Pick:
    """What the one-click UI should actually enable.

    `model` is the choice; `already_present` means no download is needed (instant);
    `upgrade` is a larger, capability-recommended model not yet downloaded (offered
    as an optional better-quality pull, not forced on a non-technical user)."""
    model: str
    already_present: bool
    upgrade: str | None = None


def smart_pick(d: Diagnosis) -> Pick:
    """Choose the model to enable on one click. Prefer something already
    downloaded so a non-technical user isn't stuck on a multi-GB first pull;
    surface the hardware-recommended model as an optional upgrade.

    Priority:
      1. the hardware recommendation, if it's already pulled;
      2. else the largest already-pulled model that fits the memory budget
         (with the recommendation offered as an upgrade);
      3. else the recommendation (which will need to be downloaded)."""
    rec = d.recommended or "llama3.2:3b"
    present = [
        m for m in d.ollama_models
        if m and not m.startswith(d.embed_recommended)   # skip the embedder
    ]
    if rec in d.ollama_models:
        return Pick(rec, True, None)

    def fits(tag: str) -> bool:
        g = est_size_gb(tag)
        return d.budget_gb is None or g is None or g <= d.budget_gb

    ranked = sorted((m for m in present if fits(m)),
                    key=lambda m: (est_size_gb(m) or 0.0), reverse=True)
    if ranked:
        best = ranked[0]
        return Pick(best, True, rec if rec != best else None)
    return Pick(rec, False, None)


def diagnose() -> Diagnosis:
    system = platform.system()
    arch = platform.machine()
    apple = system == "Darwin" and arch in ("arm64", "aarch64")
    ram = total_ram_gb()
    vram = nvidia_vram_gb()
    installed, running, models = ollama_status()
    budget = _budget_gb(ram, apple, vram)
    rec, too_big = recommend_model(budget)
    return Diagnosis(
        os=f"{system} {platform.release()}".strip(), arch=arch,
        cpus=__import__("os").cpu_count(), ram_gb=ram, apple_silicon=apple,
        nvidia_vram_gb=vram, ollama_installed=installed, ollama_running=running,
        ollama_models=models, budget_gb=budget, recommended=rec, too_big=too_big,
    )


def render(d: Diagnosis) -> str:
    ram = f"{d.ram_gb:g} GB" if d.ram_gb else "unknown"
    gpu = (f"NVIDIA {d.nvidia_vram_gb:g} GB VRAM" if d.nvidia_vram_gb
           else ("Apple Silicon (Metal, unified memory)" if d.apple_silicon else "no dedicated GPU detected"))
    note = next((n for tag, _g, n in CATALOG if tag == d.recommended), "")
    has_rec = d.recommended in d.ollama_models

    lines = [
        "🩺 agent-os doctor",
        f"   Machine : {d.os} · {d.arch} · {d.cpus or '?'} CPUs",
        f"   Memory  : {ram}",
        f"   GPU     : {gpu}",
        f"   Budget  : ~{d.budget_gb:g} GB usable for a local model" if d.budget_gb
        else "   Budget  : unknown (couldn't read memory)",
        "",
        f"   Ollama  : {'installed' if d.ollama_installed else 'NOT installed'}"
        f" · {'running' if d.ollama_running else 'not running'}"
        f"{' · ' + str(len(d.ollama_models)) + ' model(s)' if d.ollama_models else ''}",
        "",
        f"✅ Recommended model: {d.recommended}   ({note})",
    ]
    if not d.ollama_installed:
        lines += ["", "Next steps:",
                  "  1. Install Ollama (free):  https://ollama.com",
                  f"  2. Pull the model:  ollama pull {d.recommended}",
                  f"  3. Enable it:  export AGENT_OS_PROVIDER=ollama:{d.recommended}",
                  f"  4. (optional) embeddings for the Brain:  ollama pull {d.embed_recommended}"]
    elif not has_rec:
        lines += ["", "Next steps:",
                  f"  1. Pull it:  ollama pull {d.recommended}",
                  f"  2. Enable it:  export AGENT_OS_PROVIDER=ollama:{d.recommended}",
                  f"  3. (optional) embeddings:  ollama pull {d.embed_recommended}"]
    else:
        lines += ["", "You already have it. Enable it:",
                  f"  export AGENT_OS_PROVIDER=ollama:{d.recommended}"]
    if d.too_big:
        lines += ["", f"Too big for this machine: {', '.join(d.too_big)}"]
    return "\n".join(lines)
