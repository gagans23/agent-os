"""
health — structured health checks for the platform.

Verifies the things that must be true for the platform to function: the eval
gate is importable, the job/memory stores are reachable, the traces dir is
writable, skills load, and there's free disk. Returns a structured report so
`/health` and `/status` can show it and a supervisor can act on it.

No external network calls.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"  # severity if NOT ok: warn | fail


@dataclass
class HealthReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def status(self) -> str:
        if self.healthy:
            return "ok"
        if any((not c.ok and c.severity == "fail") for c in self.checks):
            return "down"
        return "degraded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [c.__dict__ for c in self.checks],
        }

    def render(self) -> str:
        lines = [f"Health: {self.status.upper()}"]
        for c in self.checks:
            mark = "ok " if c.ok else ("WARN" if c.severity == "warn" else "FAIL")
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        return "\n".join(lines)


def _check_import_ninja() -> Check:
    try:
        import ninja_harness  # noqa: F401
        return Check("ninja_harness", True, f"v{ninja_harness.__version__}")
    except Exception as exc:  # noqa: BLE001
        return Check("ninja_harness", False, f"import failed: {exc}", severity="fail")


def _check_sqlite(path: Path, name: str) -> Check:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.execute("SELECT 1")
        con.close()
        return Check(name, True, str(path))
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{exc}", severity="fail")


def _check_writable(path: Path, name: str) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".health_probe"
        probe.write_text("ok")
        probe.unlink()
        return Check(name, True, f"writable: {path}")
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"not writable: {exc}", severity="fail")


def _check_skills(skills_dir: Path) -> Check:
    try:
        from agent_os.skill_registry import SkillRegistry
        n = len(SkillRegistry(skills_dir).all())
        return Check("skills", n > 0, f"{n} skill(s) loaded",
                     severity="warn")
    except Exception as exc:  # noqa: BLE001
        return Check("skills", False, f"{exc}", severity="warn")


def _check_disk(path: Path, min_free_mb: int = 100) -> Check:
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        free_mb = usage.free // (1024 * 1024)
        return Check("disk", free_mb >= min_free_mb, f"{free_mb} MB free", severity="warn")
    except Exception as exc:  # noqa: BLE001
        return Check("disk", False, f"{exc}", severity="warn")


def run_health_checks(state_dir: str | Path = "agent_state",
                      skills_dir: str | Path = "skills",
                      traces_dir: str | Path = "traces") -> HealthReport:
    state = Path(state_dir)
    return HealthReport(checks=[
        _check_import_ninja(),
        _check_sqlite(state / "jobs.db", "jobs_db"),
        _check_sqlite(state / "state.db", "memory_db"),
        _check_writable(Path(traces_dir), "traces_dir"),
        _check_skills(Path(skills_dir)),
        _check_disk(state),
    ])
