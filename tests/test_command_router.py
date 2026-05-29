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
    assert "/setup" in router.handle("/help")
    assert "Unknown command" in router.handle("/nope")


def test_setup_is_read_only_guidance(router, monkeypatch) -> None:
    # /setup returns step-by-step guidance; it never executes (execution is
    # CLI-only via `agent-os setup --run`, per default-deny).
    from agent_os import onboarding

    monkeypatch.setattr(onboarding, "guidance",
                        lambda *a, **k: "🚀 step 1 … ollama pull llama3.2:3b")
    out = router.handle("/setup")
    assert "ollama pull" in out


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


def test_health_command(router) -> None:
    out = router.handle("/health")
    assert "Health:" in out


def test_learn_and_ask_brain(router) -> None:
    out = router.handle("/learn To add fractions with the same denominator, add the numerators. 1/4 + 2/4 = 3/4.")
    assert "Learned" in out and "chunk" in out
    answer = router.handle("/ask how do I add fractions")
    assert "numerator" in answer.lower() or "fraction" in answer.lower()


def test_ask_without_knowledge(router) -> None:
    assert "knowledge base" in router.handle("/ask anything at all").lower()


def test_audit_records_every_command_and_chain_intact(router) -> None:
    router.handle("/ping")
    router.handle("/skills")
    out = router.handle("/audit")
    assert "chain ✅ intact" in out
    # audit recorded the prior commands (plus this /audit call)
    assert router.audit.count() >= 3


def test_error_boundary_no_stack_trace(router, monkeypatch) -> None:
    # Force a handler to blow up; the router should return a friendly message.
    def boom(*a):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(router, "_skills", boom)
    out = router.handle("/skills")
    assert out.startswith("⚠️") and "kaboom" in out
    # and it was audited as an error
    assert any("error" in e["decision"] for e in router.audit.recent())


def test_digest_command_runs_and_scores(router) -> None:
    out = router.handle("/digest")
    assert "Cross-episode insights" in out
    assert "Job" in out and "score" in out
    # a digest job was persisted + evaluated
    jobs = router.jobs.list()
    assert len(jobs) == 1
    assert jobs[0]["ninja_score"] is not None


# --- Level 3: controlled autonomy ------------------------------------------

def test_risk_command(router) -> None:
    assert "REQUIRES APPROVAL" in router.handle("/risk send a whatsapp message")
    assert "auto-run" in router.handle("/risk summarize the inbox")


def test_pluggable_policy_overrides_default(tmp_path) -> None:
    from agent_os.risk import RiskAssessment, RiskLevel

    def deny_all(command, tools=None):
        return RiskAssessment(level=RiskLevel.WRITE, requires_approval=True,
                              reason="org policy: everything needs approval")

    r = CommandRouter(
        jobs=JobStore(tmp_path / "jobs.db"),
        memory=AgentMemory(tmp_path / "state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder(tmp_path / "traces"),
        policy=deny_all,
    )
    try:
        # A normally-read-only task is now gated because the custom policy says so.
        out = r.handle("/run summarize the latest research")
        assert "Needs approval" in out
        assert "org policy" in out
        assert len(r.approvals.list(status="pending")) == 1
    finally:
        r.close()


def test_default_hooks_redact_persisted_run_output(tmp_path) -> None:
    def leaky_agent(command, context, job):
        return "the secret is sk-abcdefghijklmnopqrstuvwx after summarizing the research"

    r = CommandRouter(
        jobs=JobStore(tmp_path / "jobs.db"),
        memory=AgentMemory(tmp_path / "state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder(tmp_path / "traces"),
        agent_fn=leaky_agent,
    )
    try:
        r.handle("/run summarize the latest research")
        # The default redaction hook scrubs the secret before it is persisted.
        saved = next((tmp_path / "traces").glob("**/final.md")).read_text()
        assert "sk-abcdefghijklmnopqrstuvwx" not in saved
        assert "[REDACTED:openai-key]" in saved
    finally:
        r.close()


def test_run_read_only_auto_executes(router) -> None:
    out = router.handle("/run summarize the latest research")
    assert "auto-run" in out
    assert "Ninja score" in out
    # a job was created
    assert len(router.jobs.list()) == 1
    # metering line is appended (latency + token estimate)
    assert "tok" in out


def test_cost_command_aggregates(router) -> None:
    assert "No metered runs" in router.handle("/cost")
    router.handle("/run summarize the latest research")
    out = router.handle("/cost")
    assert "Cost & usage" in out and "tokens" in out and "est. cost" in out


def test_run_write_enqueues_for_approval(router) -> None:
    out = router.handle("/run delete the old records")
    assert "Needs approval" in out and "WRITE" in out
    # no job yet; one pending approval
    assert router.jobs.list() == []
    assert len(router.approvals.list(status="pending")) == 1


def test_approve_executes_and_reject_cancels(router) -> None:
    router.handle("/run send a status message to the team")
    pending = router.approvals.list(status="pending")
    aid = pending[0]["id"]
    # approve → executes (creates a job) and marks approved
    out = router.handle(f"/approve {aid}")
    assert "Approved & executed" in out
    assert router.approvals.get(aid)["status"] == "approved"
    assert len(router.jobs.list()) == 1

    # a second task, then reject it
    router.handle("/run deploy to production")
    aid2 = router.approvals.list(status="pending")[0]["id"]
    out2 = router.handle(f"/reject {aid2}")
    assert "Rejected" in out2
    assert router.approvals.get(aid2)["status"] == "rejected"


def test_pending_lists(router) -> None:
    router.handle("/run delete things")
    assert "Pending approvals" in router.handle("/pending")


def test_approve_unknown(router) -> None:
    assert "No approval found" in router.handle("/approve zzzz")


# --- Module 2: model onboarding --------------------------------------------

def test_model_command_deterministic_by_default(router) -> None:
    out = router.handle("/model")
    assert "deterministic mode" in out
    assert "AGENT_OS_PROVIDER" in out


def test_model_command_with_provider(tmp_path) -> None:
    from agent_os.providers import EchoProvider

    r = CommandRouter(
        jobs=JobStore(tmp_path / "jobs.db"),
        memory=AgentMemory(tmp_path / "state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder(tmp_path / "traces"),
        provider=EchoProvider(),
    )
    try:
        assert "echo" in r.handle("/model")
        # A configured provider powers the Brain: learned chunks get embedded.
        r.handle("/learn fractions add the numerators when denominators match")
        assert r.context.stats()["embeddings"] >= 1
    finally:
        r.close()
