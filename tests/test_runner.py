"""Tests for the run→trace→evaluate→propose loop and improvement proposals."""

from __future__ import annotations

from agent_os.agent_memory import AgentMemory
from agent_os.improvement import propose_improvement
from agent_os.runner import run_job
from agent_os.skill_registry import SkillRegistry
from agent_os.trace_recorder import TraceRecorder


def _clean_agent(command, context, job):
    job.add_step("plan", "do it")
    job.add_tool_call("browser_open", {"url": "x"}, result="ok", status="success")
    return ("Browser demo completed: opened the page, extracted the top stories, "
            "and saved a screenshot and report. Themes were tooling and productivity.")


def _noisy_agent(command, context, job):
    return "ERROR: boom\nTraceback (most recent call last):\nWARNING: deprecated\n" * 3


def _harness(tmp_path):
    return dict(
        memory=AgentMemory(tmp_path / "state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder(tmp_path / "traces"),
    )


def test_run_job_clean_produces_report_and_summary(tmp_path) -> None:
    res = run_job("research the browser demo", _clean_agent, profile="researcher", **_harness(tmp_path))
    assert res.result is not None
    assert res.report_path and res.report_path.endswith("ninja_report.json")
    assert "Ninja score:" in res.summary
    assert res.skill is not None  # 'browser' triggers browser-research
    # outcome recorded in memory
    mem = AgentMemory(tmp_path / "state")
    assert mem.recent_outcomes()[0]["job_id"] == res.job_id
    mem.close()


def test_run_job_weak_run_yields_proposal(tmp_path) -> None:
    res = run_job("do a thing", _noisy_agent, profile="operator", **_harness(tmp_path))
    # operator threshold is 90; a noisy/ungrounded answer should fall below it
    assert res.proposal is not None
    assert res.proposal.approved is False
    assert res.proposal.requires_human_approval if hasattr(res.proposal, "requires_human_approval") else True
    d = res.proposal.to_dict()
    assert d["requires_human_approval"] is True
    assert d["memory_suggestion"]


def test_propose_improvement_none_when_strong() -> None:
    class _R:
        ninja_score = 95.0
        run_id = "r"
        metric_results: list = []
        top_failure_reasons: list = []
    assert propose_improvement(_R(), threshold=85.0) is None


def test_no_eval_skips_harness(tmp_path) -> None:
    res = run_job("x", _clean_agent, profile="qa", evaluate=False, **_harness(tmp_path))
    assert res.result is None
    assert res.report_path is None
    assert res.certification == "UNKNOWN"
