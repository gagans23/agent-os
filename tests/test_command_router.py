"""Tests for the command router (the WhatsApp-style command surface)."""

from __future__ import annotations

import pytest

from agent_os.agent_memory import AgentMemory
from agent_os.command_router import CommandRouter
from agent_os.jobs import JobStore
from agent_os.skill_registry import SkillRegistry
from agent_os.trace_recorder import TraceRecorder


@pytest.fixture
def router(tmp_path):
    r = CommandRouter(
        jobs=JobStore(tmp_path / "jobs.db"),
        memory=AgentMemory(tmp_path / "state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder(tmp_path / "traces"),
    )
    yield r
    r.close()


def test_ping(router) -> None:
    assert "pong" in router.handle("/ping").lower()


def test_help_and_unknown(router) -> None:
    assert "/status" in router.handle("/help")
    assert "Unknown command" in router.handle("/nope")


def test_agents_lists_profiles(router) -> None:
    out = router.handle("/agents")
    assert "researcher" in out and "operator" in out and "qa" in out


def test_skills_lists_skills(router) -> None:
    out = router.handle("/skills")
    assert "browser-research" in out


def test_browser_demo_runs_and_persists(router) -> None:
    out = router.handle("/browser-demo")
    assert "Ninja score" in out
    # a job should now exist
    jobs = router.jobs.list()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "done"


def test_job_and_trace_after_demo(router) -> None:
    router.handle("/browser-demo")
    job_id = router.jobs.list()[0]["job_id"]
    short = job_id[-8:]
    job_out = router.handle(f"/job {short}")
    assert "command" in job_out and "score" in job_out
    trace_out = router.handle(f"/trace {short}")
    assert "Trace" in trace_out and "steps" in trace_out


def test_job_not_found(router) -> None:
    assert "No job found" in router.handle("/job zzzzzz")


def test_job_requires_arg(router) -> None:
    assert "Usage" in router.handle("/job")


def test_status_and_eval_fallback(router) -> None:
    router.handle("/browser-demo")
    status = router.handle("/status")
    assert "Jobs:" in status
    # No suite configured → /eval falls back to job stats
    eval_out = router.handle("/eval")
    assert "Eval" in eval_out or "pass rate" in eval_out
