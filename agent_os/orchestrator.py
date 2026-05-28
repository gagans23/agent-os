"""
orchestrator — the governed swarm (Module 6).

One goal → **decompose** into independent sub-tasks → run them **in parallel**
through the SAME governed pipeline as a single job (each sub-task is traced,
risk-gated, grounded, and Ninja-scored) → a coordinator **synthesizes** one
deliverable.

This is the Kimi-Agent-Swarm pattern (decompose → parallel → synthesize) placed
*under* agent-os's trust spine, and kept honest:

  - **Local-first & your model.** Sub-agents call whatever `AGENT_OS_PROVIDER` you
    set (Ollama by default). Nothing is hardwired to a vendor or a hosted service,
    and your data never leaves your machine.
  - **Honest concurrency.** A bounded worker pool (`concurrency`, default 4) sized
    to your machine and your provider's rate limits — not a fictional "300".
  - **Default-deny.** Only read-only sub-tasks auto-run; any sub-task that
    writes/sends/deploys is **gated** (never auto-executed by the swarm).
  - **Verified.** Every sub-task is a real job (queryable via `/job`, `/trace`),
    and the synthesis is itself scored by Ninja Harness, so weak syntheses get
    flagged instead of silently shipped.

Decomposition uses your model when one is configured; with no model it falls back
to splitting a goal that already enumerates its items (lines / "1." / ";"). Real
open-ended decomposition needs a model — we don't fake it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_os.risk import classify_risk
from agent_os.runner import run_job
from agent_os.skill_registry import SkillRegistry

AgentFn = Callable[[str, str, Any], str]


@dataclass
class SubTask:
    title: str
    task: str


@dataclass
class SubResult:
    title: str
    task: str
    job_id: str | None
    verdict: str          # PASS/WARN/FAIL, or "GATED" / "ERROR"
    score: float
    output: str
    risk: str = "READ_ONLY"
    gated: bool = False
    error: str = ""


@dataclass
class SwarmResult:
    goal: str
    results: list[SubResult] = field(default_factory=list)
    deliverable: str = ""
    synthesis_job_id: str | None = None
    synthesis_score: float = 0.0

    @property
    def done(self) -> list[SubResult]:
        return [r for r in self.results if not r.gated and not r.error]

    @property
    def gated(self) -> list[SubResult]:
        return [r for r in self.results if r.gated]

    @property
    def failed(self) -> list[SubResult]:
        return [r for r in self.results if r.error]

    def render(self) -> str:
        lines = [
            f"🐝 Swarm: {self.goal}",
            f"   {len(self.results)} sub-task(s) · {len(self.done)} done · "
            f"{len(self.gated)} gated · {len(self.failed)} failed",
        ]
        for r in self.results:
            if r.gated:
                tag = f"GATED:{r.risk}"
            elif r.error:
                tag = "ERROR"
            else:
                tag = f"{r.verdict} {r.score:.0f}"
            lines.append(f"   - [{tag}] {r.title}")
        if self.gated:
            lines.append("   (gated sub-tasks need approval — run them via /run)")
        if self.synthesis_job_id:
            lines.append(f"\nSynthesis scored {self.synthesis_score:.1f} "
                         f"(Job {self.synthesis_job_id[-8:]}, try /trace {self.synthesis_job_id[-8:]})")
        lines.append("\n--- Deliverable ---\n" + (self.deliverable or "(empty)"))
        return "\n".join(lines)


def _parse_subtasks(raw: str) -> list[SubTask]:
    """Tolerantly parse a model reply into sub-tasks (expects a JSON array)."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("["):
        bracket = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket:
            text = bracket.group(0)
    data = json.loads(text)
    out: list[SubTask] = []
    for item in data:
        if isinstance(item, dict):
            task = str(item.get("task") or item.get("title") or "").strip()
            title = str(item.get("title") or task)[:80]
        else:
            task = str(item).strip()
            title = task[:80]
        if task:
            out.append(SubTask(title, task))
    return out


def _split_enumerated(goal: str) -> list[str]:
    """Split a goal that already enumerates items (lines, then ';')."""
    raw = [ln.strip() for ln in goal.splitlines()]
    items = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", ln) for ln in raw if ln]
    if len(items) <= 1:
        items = [p.strip() for p in goal.split(";") if p.strip()]
    return [it for it in items if it]


class Orchestrator:
    """Run a goal as a governed swarm of parallel, traced, scored sub-jobs."""

    def __init__(self, *, provider=None, agent_fn: AgentFn | None = None,
                 concurrency: int = 4, skills: SkillRegistry | None = None,
                 state_dir: str | Path = "agent_state",
                 traces_dir: str | Path = "traces", jobs_db: str | Path | None = None,
                 audit=None, max_subtasks: int = 64, default_n: int = 6,
                 score_synthesis: bool = True) -> None:
        self.provider = provider
        self.concurrency = max(1, int(concurrency))
        self.skills = skills if skills is not None else SkillRegistry()
        self.state_dir = str(state_dir)
        self.traces_dir = str(traces_dir)
        self.jobs_db = str(jobs_db) if jobs_db else f"{self.state_dir}/jobs.db"
        self.audit = audit
        self.max_subtasks = max_subtasks
        self.default_n = default_n
        self.score_synthesis = score_synthesis
        if agent_fn is not None:
            self.agent_fn = agent_fn
        elif provider is not None:
            self.agent_fn = provider.as_agent_fn()
        else:
            self.agent_fn = _default_agent

    # --- decomposition -----------------------------------------------------

    def decompose(self, goal: str, n: int | None = None) -> list[SubTask]:
        if self.provider is not None:
            want = n or self.default_n
            prompt = (
                f"Break this goal into at most {want} INDEPENDENT sub-tasks that can "
                "run in parallel. Return ONLY a JSON array of objects "
                '{"title": "...", "task": "..."} and no prose.\n\nGoal: ' + goal
            )
            try:
                subs = _parse_subtasks(self.provider.complete(prompt))
                if subs:
                    return subs[: self.max_subtasks]
            except Exception:  # noqa: BLE001 - fall back to deterministic split
                pass
        items = _split_enumerated(goal)
        if len(items) > 1:
            return [SubTask(it[:80], it) for it in items][: self.max_subtasks]
        return [SubTask(goal[:80], goal)]

    # --- execution ---------------------------------------------------------

    def run(self, goal: str, *, subtasks: list | None = None,
            n: int | None = None) -> SwarmResult:
        subs = self._coerce(subtasks) if subtasks else self.decompose(goal, n)
        subs = subs[: self.max_subtasks]
        self._init_shared_db()  # create WAL + schema once before fanning out
        results: list[SubResult | None] = [None] * len(subs)
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futs = {ex.submit(self._run_one, s): i for i, s in enumerate(subs)}
            for fut in as_completed(futs):
                results[futs[fut]] = fut.result()
        final = [r for r in results if r is not None]
        deliverable, sjob, sscore = self._synthesize(goal, final)
        out = SwarmResult(goal, final, deliverable, sjob, sscore)
        if self.audit is not None:
            self.audit.record(
                f"swarm: {goal}", actor="orchestrator",
                decision=f"{len(out.done)} done, {len(out.gated)} gated, "
                         f"{len(out.failed)} failed of {len(final)}",
            )
        return out

    def _init_shared_db(self) -> None:
        """Open + close the job store once so WAL mode and the schema exist before
        many worker connections open it concurrently."""
        from agent_os.jobs import JobStore

        JobStore(self.jobs_db).close()

    def _run_one(self, s: SubTask) -> SubResult:
        # Default-deny: the swarm never auto-executes a privileged sub-task.
        assessment = classify_risk(s.task)
        if assessment.requires_approval:
            return SubResult(s.title, s.task, None, "GATED", 0.0, "",
                             risk=assessment.level.label, gated=True)

        from agent_os.agent_memory import AgentMemory
        from agent_os.jobs import JobStore
        from agent_os.trace_recorder import TraceRecorder

        jobs = JobStore(self.jobs_db)
        memory = AgentMemory(self.state_dir)
        recorder = TraceRecorder(self.traces_dir)
        holder: dict[str, str] = {}
        base = self.agent_fn

        def _capture(cmd: str, ctx: str, job: Any) -> str:
            out = base(cmd, ctx, job)
            holder["out"] = out
            return out

        try:
            res = run_job(s.task, _capture, profile="researcher", memory=memory,
                          skills=self.skills, recorder=recorder, jobs=jobs)
            return SubResult(s.title, s.task, res.job_id, res.verdict,
                             res.ninja_score, holder.get("out", ""))
        except Exception as exc:  # noqa: BLE001 - one bad sub-task must not sink the swarm
            return SubResult(s.title, s.task, None, "ERROR", 0.0, "",
                             error=f"{type(exc).__name__}: {exc}")
        finally:
            jobs.close()
            memory.close()

    # --- synthesis ---------------------------------------------------------

    def _synthesize(self, goal: str, results: list[SubResult]) -> tuple[str, str | None, float]:
        done = [r for r in results if not r.gated and not r.error and r.output]
        if not done:
            return f"# {goal}\n\n(no completed sub-tasks to synthesize)", None, 0.0

        if self.provider is not None:
            blocks = "\n\n".join(f"### {r.title}\n{r.output}" for r in done)
            deliverable = self.provider.complete(
                "Synthesize ONE coherent deliverable for the goal below, using only "
                f"what the sub-results contain.\n\nGoal: {goal}\n\n{blocks}"
            )
        else:
            deliverable = f"# {goal}\n\n" + "\n\n".join(
                f"## {r.title}\n{r.output}" for r in done)

        if not self.score_synthesis:
            return deliverable, None, 0.0

        # Score the synthesis as its own job; references = sub-results (grounding).
        refs = [r.output for r in done]
        try:
            from ninja_harness.schemas import EvaluationCase
            case = EvaluationCase(task=goal, references=refs)
        except Exception:  # noqa: BLE001 - ninja-harness optional
            case = None

        from agent_os.agent_memory import AgentMemory
        from agent_os.jobs import JobStore
        from agent_os.trace_recorder import TraceRecorder

        jobs = JobStore(self.jobs_db)
        memory = AgentMemory(self.state_dir)
        recorder = TraceRecorder(self.traces_dir)

        def _syn(cmd: str, ctx: str, job: Any) -> str:
            for r in done:
                job.add_step("observation", f"{r.title}: {r.output[:60]}")
            return deliverable

        try:
            res = run_job(f"swarm synthesis: {goal}", _syn, profile="researcher",
                          memory=memory, skills=self.skills, recorder=recorder,
                          jobs=jobs, case=case)
            return deliverable, res.job_id, res.ninja_score
        except Exception:  # noqa: BLE001
            return deliverable, None, 0.0
        finally:
            jobs.close()
            memory.close()

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _coerce(subtasks: list) -> list[SubTask]:
        out: list[SubTask] = []
        for item in subtasks:
            if isinstance(item, SubTask):
                out.append(item)
            elif isinstance(item, dict):
                task = str(item.get("task") or item.get("title") or "").strip()
                out.append(SubTask(str(item.get("title") or task)[:80], task))
            else:
                out.append(SubTask(str(item)[:80], str(item)))
        return [s for s in out if s.task]


def _default_agent(command: str, context: str, job: Any) -> str:
    """Offline default when no provider/agent is configured (honest placeholder)."""
    try:
        job.add_step("action", "composed a response (no model configured)")
    except Exception:  # noqa: BLE001
        pass
    return f"(no model configured) {command}"
