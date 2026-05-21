"""
daily_eval — produce a daily reliability summary.

If an eval suite is configured, runs it through Ninja Harness and returns the
compact summary. Otherwise summarizes the persisted job outcomes (counts, pass
rate, recent flagged runs). Designed to be run on a schedule (cron / systemd
timer / GitHub Action) and piped to your notifier.

    summary = daily_summary(state_dir="agent_state")
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_os.jobs import JobStore


def _find_suite(suite_path: str | None) -> str | None:
    if suite_path and Path(suite_path).exists():
        return suite_path
    env = os.environ.get("AGENT_OS_SUITE")
    if env and Path(env).exists():
        return env
    for candidate in ("evals/suite.yaml", "evals/suite.yml"):
        if Path(candidate).exists():
            return candidate
    return None


def _suite_summary(suite: str) -> str | None:
    try:
        from ninja_harness.datasets.loader import load_suite
        from ninja_harness.report import generate_suite_summary
        from ninja_harness.runner import SuiteRunner

        result = SuiteRunner().run_suite(load_suite(suite))
        return generate_suite_summary(result)
    except Exception:  # noqa: BLE001
        return None


def _jobs_summary(state_dir: str | Path) -> str:
    store = JobStore(Path(state_dir) / "jobs.db")
    try:
        stats = store.stats()
        recent = store.list(limit=20)
        flagged = [j for j in recent if j.get("flagged")]
        lines = [
            "Daily agent-os eval",
            f"  jobs: {stats['total']} · pass rate {stats['pass_rate']:.0%}",
        ]
        if stats["by_certification"]:
            dist = " ".join(f"{k}:{v}" for k, v in stats["by_certification"].items())
            lines.append(f"  by cert: {dist}")
        if flagged:
            lines.append(f"  flagged (need attention): {len(flagged)}")
            for j in flagged[:5]:
                lines.append(f"    - {j['job_id'][-8:]} {j.get('verdict')} "
                             f"{(j.get('ninja_score') or 0):.0f}  {j['command'][:40]}")
        else:
            lines.append("  no flagged runs ✅")
        return "\n".join(lines)
    finally:
        store.close()


def daily_summary(state_dir: str | Path = "agent_state", suite_path: str | None = None) -> str:
    """Return a daily reliability summary (suite if configured, else job stats)."""
    suite = _find_suite(suite_path)
    if suite:
        summary = _suite_summary(suite)
        if summary:
            return summary
    return _jobs_summary(state_dir)
