"""
runner — the /run loop:

    command → profile → memory context → skill match → execute (agent_fn)
    → record trace → Ninja Harness evaluates → record outcome
    → propose improvement (if weak) → WhatsApp-style summary

The agent itself is supplied as a callable (`agent_fn`) so this stays
framework-agnostic: bring your researcher/operator/builder/qa agent, and the
runner handles tracing, evaluation gating, memory, and improvement proposals.
Ninja Harness is the evaluation gate.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_os.agent_memory import AgentMemory
from agent_os.hooks import HookContext, HookPhase, HookRegistry
from agent_os.improvement import ImprovementProposal, propose_improvement
from agent_os.jobs import JobStore
from agent_os.metering import estimate_tokens
from agent_os.profiles import AgentProfile, get_profile
from agent_os.skill_registry import Skill, SkillRegistry
from agent_os.trace_recorder import JobRecorder, TraceRecorder

# An agent: given the command, a memory-context string, and the live recorder
# (so it can log steps/tool calls/screenshots), return the final answer text.
AgentFn = Callable[[str, str, JobRecorder], str]


@dataclass
class JobResult:
    job_id: str
    certification: str       # Ninja Harness certification (PASS/WARN/FAIL)
    verdict: str             # platform verdict incl. the profile threshold
    ninja_score: float
    flagged: bool            # True if below the profile threshold (proposal exists)
    result: Any  # ninja_harness EvaluationResult (or None if eval skipped)
    skill: Skill | None
    proposal: ImprovementProposal | None
    trace_path: str
    report_path: str | None
    summary: str
    latency_s: float = 0.0       # wall time spent in the agent (the model call)
    in_tokens: int = 0           # estimated input tokens (command + context)
    out_tokens: int = 0          # estimated output tokens (final answer)


def _evaluate(trace: dict, case_path: str | None, case: Any = None):
    """Run Ninja Harness against a trace dict. Imported lazily so the rest of
    agent-os works even if ninja-harness isn't installed. An in-memory `case`
    (a ninja_harness EvaluationCase) takes precedence over `case_path`."""
    from ninja_harness.adapters import detect_adapter
    from ninja_harness.scoring.ninja_score import NinjaScoreAggregator

    run = detect_adapter(trace).parse(trace)
    if case is None and case_path:
        from ninja_harness.datasets.loader import load_eval_case

        case = load_eval_case(case_path)
    return NinjaScoreAggregator().evaluate(run, case)


def _whatsapp_summary(verdict: str, result: Any, proposal: ImprovementProposal | None,
                      artifact: str) -> str:
    if result is None:
        return f"Job complete.\n\nResult: (not evaluated)\nArtifact: {artifact}"
    safety = result.metric_by_name("safety")
    safety_txt = "PASS" if (not safety or not safety.is_applicable or safety.passed) else "FAIL"
    weakness = ""
    if proposal and proposal.reasons:
        weakness = f"\nWeakness: {proposal.reasons[0]}"
    elif result.top_failure_reasons:
        weakness = f"\nWeakness: {result.top_failure_reasons[0]}"
    return (
        "Job complete.\n\n"
        f"Result: {verdict}\n"
        f"Ninja score: {result.ninja_score:.1f}\n"
        f"Safety: {safety_txt}"
        f"{weakness}\n"
        f"Artifact: {artifact}"
    )


def run_job(
    command: str,
    agent_fn: AgentFn,
    *,
    profile: str | AgentProfile = "researcher",
    memory: AgentMemory | None = None,
    skills: SkillRegistry | None = None,
    recorder: TraceRecorder | None = None,
    jobs: JobStore | None = None,
    case_path: str | None = None,
    case: Any = None,
    evaluate: bool = True,
    hooks: HookRegistry | None = None,
) -> JobResult:
    """Execute one job end-to-end with tracing, evaluation, and an improvement
    proposal. Pure orchestration — no external services are called here.

    If a JobStore is provided, the job is persisted (running → done/failed) so it
    survives restarts and can be looked up later by id."""
    prof = profile if isinstance(profile, AgentProfile) else get_profile(profile)
    memory = memory or AgentMemory()
    skills = skills or SkillRegistry()
    recorder = recorder or TraceRecorder()
    hooks = hooks if hooks is not None else HookRegistry.default()

    skill = skills.match(command)
    context = memory.context_for(command)
    if skill:
        context += f"\n\n## Matched skill: {skill.name}\n{skill.procedure}"

    job = recorder.start(command, agent_name=prof.name, task=command)
    job.set_metadata(profile=prof.name, skill=skill.name if skill else None)
    if jobs is not None:
        jobs.create(job.job_id, command, profile=prof.name, skill=skill.name if skill else "")

    # BEFORE hooks: may rewrite the context the agent sees (e.g. redact secrets).
    hctx = HookContext(phase=HookPhase.BEFORE, command=command, profile=prof.name,
                       job_id=job.job_id, context=context)
    context = hooks.run_before(hctx).context

    _t0 = time.perf_counter()
    try:
        final = agent_fn(command, context, job)
    except Exception as exc:  # noqa: BLE001 - record the failure durably
        if jobs is not None:
            jobs.finish(job.job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    latency_s = round(time.perf_counter() - _t0, 3)

    # AFTER hooks: may rewrite the output before it's traced/scored/persisted.
    hctx.phase = HookPhase.AFTER
    hctx.context = context
    hctx.output = final
    final = hooks.run_after(hctx).output or ""

    in_tokens = estimate_tokens(f"{command}\n{context}")
    out_tokens = estimate_tokens(final or "")
    job.set_final(final)
    trace_path = job.save_trace()

    result = None
    report_path = None
    proposal = None
    if evaluate:
        result = _evaluate(job.to_trace(), case_path, case=case)
        report_path = str(job.save_report(result))
        memory.record_outcome(
            job.job_id, command, result.ninja_score, result.certification,
            profile=prof.name, skill=skill.name if skill else "",
        )
        proposal = propose_improvement(
            result, job_id=job.job_id, threshold=prof.pass_threshold,
            skill_name=skill.name if skill else None,
        )

    memory.save_session(job.job_id, {
        "command": command,
        "profile": prof.name,
        "skill": skill.name if skill else None,
        "certification": result.certification if result else None,
        "ninja_score": result.ninja_score if result else None,
        "proposal": proposal.to_dict() if proposal else None,
        "latency_s": latency_s,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
    })

    # Platform verdict honors the profile threshold: a Ninja-PASS run that falls
    # below the profile's pass_threshold is downgraded to WARN (and flagged).
    flagged = proposal is not None
    certification = result.certification if result else "UNKNOWN"
    if certification == "PASS" and flagged:
        verdict = "WARN"
    else:
        verdict = certification

    if jobs is not None:
        jobs.finish(
            job.job_id,
            status="done",
            ninja_score=result.ninja_score if result else None,
            certification=certification if result else None,
            verdict=verdict if result else None,
            flagged=flagged,
            trace_path=str(trace_path),
            report_path=report_path,
        )

    summary = _whatsapp_summary(
        verdict, result, proposal,
        artifact=str(job.dir / "final.md"),
    )

    return JobResult(
        job_id=job.job_id,
        certification=certification,
        verdict=verdict,
        ninja_score=result.ninja_score if result else 0.0,
        flagged=flagged,
        result=result,
        skill=skill,
        proposal=proposal,
        trace_path=str(trace_path),
        report_path=report_path,
        summary=summary,
        latency_s=latency_s,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
    )
