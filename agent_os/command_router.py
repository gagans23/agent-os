"""
command_router — map a command string to a text response.

This is the transport-agnostic command surface (the live WhatsApp/Cloudflare
transport is a later level). A gateway hands the router a raw command like
"/job f6df6f7d" and gets back a plain-text reply suitable for WhatsApp.

Level 1 commands:
    /ping                 liveness
    /status               health + recent jobs
    /agents               list agent profiles
    /skills               list skills
    /eval                 run the configured Ninja Harness suite (or summarize jobs)
    /browser-demo         run the built-in researcher demo through the full loop
    /job <id>             show a persisted job record (id or short prefix)
    /trace <id>           show a job's trace summary (steps, tools, score)
    /help                 list commands

Read-only by design. No approvals, sends, or self-modification here.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_os import __version__
from agent_os.agent_memory import AgentMemory
from agent_os.jobs import JobStore
from agent_os.profiles import PROFILES
from agent_os.skill_registry import SkillRegistry
from agent_os.trace_recorder import JobRecorder, TraceRecorder


def _demo_browser_agent(command: str, context: str, job: JobRecorder) -> str:
    """Built-in researcher demo so /browser-demo works without external services."""
    job.add_step("plan", "Open Hacker News and extract the top stories.")
    job.add_tool_call("browser_open", {"url": "https://news.ycombinator.com"},
                      result="ok", status="success")
    job.add_tool_call("save_artifact", {"name": "report.md"}, result="saved", status="success")
    job.add_screenshot("home.txt", data=b"(screenshot placeholder)")
    return (
        "Browser demo completed: opened Hacker News, extracted the top stories, "
        "searched DuckDuckGo for context, and saved a screenshot and report. Top "
        "themes today were open-source tooling and developer productivity. Raw "
        "headlines and logs are kept in the report, not this summary."
    )


def _default_agent(command: str, context: str, job: JobRecorder) -> str:
    """Safe default agent for /run. Composes an answer; performs no external action.
    Replace with your real agents (researcher/operator/builder) per profile."""
    job.add_step("plan", f"Handle task: {command[:80]}")
    job.add_step("action", "Composed a response (default agent — no external side effects).")
    return f"Handled: {command}"


def _demo_episodes():
    """Built-in demo episodes so /digest runs without a feed fetcher.
    In production, supply `digest_source=` returning EpisodeSummary objects."""
    from agent_os.insights import EpisodeSummary

    return [
        EpisodeSummary("acquired-vanguard", "Acquired",
                       "Vanguard: the communist capitalist", published="2026-05-18",
                       key_points=[
                           "Vanguard is owned by its fund customers, aligning incentives with investors.",
                           "Durable outcomes came from redesigning incentives, not heroics."]),
        EpisodeSummary("huberman-epley", "Huberman Lab",
                       "How to Overcome Social Anxiety", published="2026-05-18",
                       key_points=[
                           "Social anxiety improves with real exposure, not simulated practice.",
                           "Durable change comes from updating incentives and feedback."]),
    ]


class CommandRouter:
    """Routes commands to handlers and returns plain-text replies."""

    def __init__(self, *, jobs: JobStore | None = None, memory: AgentMemory | None = None,
                 skills: SkillRegistry | None = None, recorder: TraceRecorder | None = None,
                 approvals=None, agent_fn=None, suite_path: str | None = None,
                 digest_source=None, reasoner=None, digest_lens: str = "founder/investor",
                 audit=None, context=None, provider=None) -> None:
        from agent_os.approvals import ApprovalStore
        from agent_os.audit import AuditLog
        from agent_os.context import ContextStore

        self.jobs = jobs or JobStore()
        self.memory = memory or AgentMemory()
        self.skills = skills or SkillRegistry()
        self.recorder = recorder or TraceRecorder()
        self.approvals = approvals or ApprovalStore(Path(self.memory.root) / "approvals.db")
        self.audit = audit or AuditLog(Path(self.memory.root) / "audit.db")
        self.context = context or ContextStore(Path(self.memory.root) / "context.db")
        self.agent_fn = agent_fn or _default_agent
        self.suite_path = suite_path
        # Cross-episode digest: supply your feed fetcher + LLM reasoner in production.
        self.digest_source = digest_source or _demo_episodes
        self.reasoner = reasoner
        self.digest_lens = digest_lens
        # Model onboarding (opt-in): a provider is used ONLY if you pass one or set
        # AGENT_OS_PROVIDER. With none configured, agent-os stays deterministic and
        # makes no model calls. A configured provider powers /ask + /run (agent_fn),
        # /digest (reasoner), and the Brain's semantic search (embedder).
        self.provider = provider
        if self.provider is None:
            try:
                from agent_os.providers import provider_from_env
                self.provider = provider_from_env()
            except Exception:  # noqa: BLE001 - a bad spec must not break the router
                self.provider = None
        if self.provider is not None:
            if agent_fn is None:
                self.agent_fn = self.provider.as_agent_fn()
            if reasoner is None:
                self.reasoner = self.provider.as_reasoner()
            try:
                self.context.embedder = self.provider.as_embedder()
                self.context.reindex_embeddings()
            except Exception:  # noqa: BLE001 - embeddings are optional; degrade to keyword
                pass

    # --- dispatch ----------------------------------------------------------

    def handle(self, text: str, actor: str = "local") -> str:
        """Route a command to its handler. Every command is audited, and a global
        error boundary turns handler exceptions into a friendly reply (never a
        raw stack trace to the user)."""
        text = (text or "").strip()
        if not text:
            return self._help()
        parts = text.split()
        cmd = parts[0].lstrip("/").lower()
        args = parts[1:]
        handler = {
            "ping": self._ping,
            "help": lambda a: self._help(),
            "status": lambda a: self._status(),
            "health": lambda a: self._health(),
            "agents": lambda a: self._agents(),
            "skills": lambda a: self._skills(),
            "eval": lambda a: self._eval(),
            "browser-demo": lambda a: self._browser_demo(),
            "digest": lambda a: self._digest(),
            "learn": self._learn,
            "ask": self._ask,
            "audit": lambda a: self._audit(),
            "model": lambda a: self._model(),
            "doctor": lambda a: self._doctor(),
            "cost": lambda a: self._cost(),
            "job": self._job,
            "trace": self._trace,
            "run": self._run,
            "swarm": self._swarm,
            "risk": self._risk,
            "pending": lambda a: self._pending(),
            "approve": self._approve,
            "reject": self._reject,
        }.get(cmd)
        if handler is None:
            self.audit.record(text, actor=actor, decision="unknown-command")
            return f"Unknown command: /{cmd}\n\n{self._help()}"
        try:
            response = handler(args)
        except Exception as exc:  # noqa: BLE001 - global boundary; never leak a stack trace
            self.audit.record(text, actor=actor, decision=f"error: {type(exc).__name__}")
            return f"⚠️ /{cmd} failed: {type(exc).__name__}: {exc}"
        self.audit.record(text, actor=actor, decision=response.splitlines()[0][:120] if response else "ok")
        return response

    # --- handlers ----------------------------------------------------------

    def _ping(self, args: list[str]) -> str:
        return f"pong ✅ agent-os {__version__}"

    def _help(self) -> str:
        return (
            "Commands:\n"
            "  /ping            liveness\n"
            "  /status          health + recent jobs\n"
            "  /health          detailed health checks\n"
            "  /agents          list agent profiles\n"
            "  /skills          list skills\n"
            "  /eval            run the eval suite (Ninja Harness)\n"
            "  /browser-demo    run the demo agent end-to-end\n"
            "  /digest          synthesize a cross-episode insight digest\n"
            "  /learn <path|text>  ingest notes/files into the knowledge base (the brain)\n"
            "  /ask <question>  answer from your knowledge base (grounded + scored)\n"
            "  /audit           recent audit entries + chain integrity\n"
            "  /model           show the configured model provider\n"
            "  /doctor          detect hardware + recommend a local model\n"
            "  /cost            cost · latency · token usage across recent runs\n"
            "  /job <id>        show a job record\n"
            "  /trace <id>      show a job's trace summary\n"
            "  /run <task>      submit a task (auto-runs if read-only; else needs approval)\n"
            "  /swarm <goal>    governed swarm: decompose → parallel sub-jobs → synthesize\n"
            "  /risk <task>     show the risk classification for a task\n"
            "  /pending         list actions awaiting approval\n"
            "  /approve <id>    approve & execute a pending action\n"
            "  /reject <id>     reject a pending action"
        )

    def _health(self) -> str:
        from agent_os.health import run_health_checks

        report = run_health_checks(
            state_dir=self.memory.root, skills_dir=self.skills.root,
            traces_dir=self.recorder.root,
        )
        return report.render()

    def _status(self) -> str:
        from agent_os.health import run_health_checks

        report = run_health_checks(
            state_dir=self.memory.root, skills_dir=self.skills.root,
            traces_dir=self.recorder.root,
        )
        stats = self.jobs.stats()
        recent = self.jobs.list(limit=5)
        lines = [
            f"agent-os {__version__} — health: {report.status.upper()}",
            f"Jobs: {stats['total']} total · pass rate {stats['pass_rate']:.0%}",
        ]
        if stats["by_certification"]:
            dist = " ".join(f"{k}:{v}" for k, v in stats["by_certification"].items())
            lines.append(f"By certification: {dist}")
        if recent:
            lines.append("\nRecent:")
            for j in recent:
                short = j["job_id"][-8:]
                lines.append(f"  {short}  {j.get('verdict') or j['status']:<5} "
                             f"{(j.get('ninja_score') or 0):.0f}  {j['command'][:40]}")
        return "\n".join(lines)

    def _agents(self) -> str:
        lines = ["Agent profiles:"]
        for p in PROFILES.values():
            lines.append(f"  {p.name:<10} (threshold {p.pass_threshold:.0f}) — {p.description}")
            lines.append(f"             tools: {', '.join(p.allowed_tools)}")
        return "\n".join(lines)

    def _skills(self) -> str:
        skills = self.skills.all()
        if not skills:
            return "No skills found."
        lines = ["Skills:"]
        for s in skills:
            lines.append(f"  {s.name} — {s.description}")
            lines.append(f"    triggers: {', '.join(s.triggers)}")
        return "\n".join(lines)

    def _eval(self) -> str:
        suite = self.suite_path or self._find_suite()
        if suite:
            try:
                from ninja_harness.datasets.loader import load_suite
                from ninja_harness.report import generate_suite_summary
                from ninja_harness.runner import SuiteRunner

                result = SuiteRunner().run_suite(load_suite(suite))
                return generate_suite_summary(result)
            except Exception as exc:  # noqa: BLE001
                return f"Eval suite failed to run ({exc}). Falling back to job stats.\n\n" + self._eval_jobs()
        return self._eval_jobs()

    def _eval_jobs(self) -> str:
        stats = self.jobs.stats()
        recent = self.jobs.list(limit=10)
        if not recent:
            return "No jobs evaluated yet. Run /browser-demo, then /eval."
        lines = [
            "Eval (recent jobs):",
            f"  {stats['total']} jobs · pass rate {stats['pass_rate']:.0%}",
        ]
        for j in recent:
            if j.get("certification"):
                lines.append(f"  {j['verdict'] or j['certification']:<5} "
                             f"{(j.get('ninja_score') or 0):.1f}  {j['command'][:40]}")
        return "\n".join(lines)

    def _find_suite(self) -> str | None:
        import os

        env = os.environ.get("AGENT_OS_SUITE")
        if env and Path(env).exists():
            return env
        for candidate in ("evals/suite.yaml", "evals/suite.yml"):
            if Path(candidate).exists():
                return candidate
        return None

    def _browser_demo(self) -> str:
        from agent_os.runner import run_job

        result = run_job(
            "browser demo: research the top Hacker News stories",
            _demo_browser_agent,
            profile="researcher",
            memory=self.memory, skills=self.skills,
            recorder=self.recorder, jobs=self.jobs,
        )
        return result.summary + f"\n\nJob: {result.job_id[-8:]}  (try /trace {result.job_id[-8:]})"

    # --- the brain: knowledge base -----------------------------------------

    def _learn(self, args: list[str]) -> str:
        if not args:
            return "Usage: /learn <file path | text to remember>"
        target = " ".join(args)
        if Path(target).expanduser().exists():
            doc_id = self.context.ingest_file(Path(target).expanduser())
            src = Path(target).name
        else:
            doc_id = self.context.ingest_text(target, source="note")
            src = "note"
        stats = self.context.stats()
        return (f"🧠 Learned from '{src}' (doc {doc_id}). "
                f"Knowledge base now has {stats['docs']} doc(s), {stats['chunks']} chunk(s). "
                f"Ask with /ask <question>.")

    def _ask(self, args: list[str]) -> str:
        if not args:
            return "Usage: /ask <question>"
        question = " ".join(args)
        ctx = self.context.build_context(question)
        if not ctx:
            return "I don't have anything in the knowledge base about that yet. Use /learn first."
        # Answer using context. With a real LLM agent_fn this becomes a true answer;
        # the default composes from retrieved context and is scored for grounding.
        refs = self.context.references(question)

        try:
            from ninja_harness.schemas import EvaluationCase
            case = EvaluationCase(task=question, references=refs)
        except ImportError:
            case = None

        holder: dict[str, str] = {}

        def _ask_agent(command, context_str, job):
            job.add_step("observation", f"Retrieved {len(refs)} context chunk(s).")
            answer = self.agent_fn(f"Answer using ONLY this context:\n{ctx}\n\nQ: {question}",
                                   context_str, job)
            # If using the trivial default agent, fall back to the context itself.
            if not answer or "Handled:" in answer:
                answer = f"Based on your notes:\n{ctx}"
            holder["answer"] = answer
            return answer

        from agent_os.runner import run_job
        result = run_job(f"ask: {question}", _ask_agent, profile="researcher",
                         memory=self.memory, skills=self.skills, recorder=self.recorder,
                         jobs=self.jobs, case=case)
        g = result.result.metric_by_name("grounding") if result.result else None
        gtxt = f" · grounding {g.score:.2f}" if g and g.is_applicable else ""
        return f"{holder['answer']}\n\n[{result.verdict}{gtxt} · Job {result.job_id[-8:]}]"

    def _audit(self) -> str:
        ok, broken = self.audit.verify()
        entries = self.audit.recent(limit=8)
        head = f"Audit log — {self.audit.count()} entries · chain {'✅ intact' if ok else f'❌ BROKEN at seq {broken}'}"
        lines = [head, ""]
        for e in entries:
            lines.append(f"  {e['ts'][11:19]}  {e['command'][:40]:<40}  → {e['decision'][:40]}")
        return "\n".join(lines)

    def _model(self) -> str:
        if self.provider is None:
            return (
                "Model: none configured — deterministic mode (no model calls).\n"
                "Plug one in (Ollama-first, free & local):\n"
                "  export AGENT_OS_PROVIDER=ollama:llama3        # local, no key\n"
                "  export AGENT_OS_PROVIDER=openai:gpt-4o-mini   # needs OPENAI_API_KEY\n"
                "  export AGENT_OS_PROVIDER=anthropic:claude-3-5-sonnet-20241022\n"
                "It powers /ask + /run (answers), /digest (synthesis), and the Brain's "
                "semantic search."
            )
        embeds = self.context.stats().get("embeddings", 0)
        return (
            f"Model: {self.provider.name}\n"
            f"  powers: /ask + /run (answers) · /digest (synthesis) · Brain semantic search\n"
            f"  embedded chunks: {embeds}"
        )

    def _doctor(self) -> str:
        from agent_os.doctor import diagnose, render

        return render(diagnose())

    def _cost(self) -> str:
        """Cost / latency / token usage rolled up across recent runs."""
        from agent_os.metering import estimate_cost, fmt_cost

        sessions = self.memory.recent_sessions(limit=50)
        metered = [s for s in sessions if s.get("latency_s") is not None]
        if not metered:
            return "No metered runs yet. Try /run or /swarm, then /cost."
        pname = self.provider.name if self.provider else "local (no model)"
        pricing_key = self.provider.name if self.provider else "ollama"
        in_tok = sum(int(s.get("in_tokens") or 0) for s in metered)
        out_tok = sum(int(s.get("out_tokens") or 0) for s in metered)
        lat = sum(float(s.get("latency_s") or 0) for s in metered)
        cost = estimate_cost(pricing_key, in_tok, out_tok)
        return (
            f"Cost & usage — last {len(metered)} run(s) · provider: {pname}\n"
            f"  tokens : ~{in_tok} in / ~{out_tok} out  (~{in_tok + out_tok} total)\n"
            f"  latency: {lat:.1f}s total · {lat / len(metered):.2f}s avg\n"
            f"  est. cost: {fmt_cost(cost)}  (estimate — verify vs. your provider's pricing)"
        )

    def _meter_line(self, result) -> str:
        from agent_os.metering import Meter

        m = Meter(result.latency_s, result.in_tokens, result.out_tokens)
        return f"[{m.line(self.provider.name if self.provider else None)}]"

    def _digest(self) -> str:
        """Synthesize a cross-episode digest, score it, and persist it as a job.
        Uses self.digest_source (feed fetcher) + self.reasoner (your LLM)."""
        from agent_os.insights import CrossEpisodeSynthesizer
        from agent_os.runner import run_job

        episodes = self.digest_source()
        if not episodes:
            return "No episodes to digest. Wire `digest_source=` to your feed fetcher."
        synth = CrossEpisodeSynthesizer(reasoner=self.reasoner, memory=self.memory)
        digest = synth.synthesize(episodes, lens=self.digest_lens)
        final, refs = digest.as_trace_inputs()

        # Grade the digest with Ninja Harness: grounding (claims vs evidence) + hygiene.
        try:
            from ninja_harness.schemas import EvaluationCase
            case = EvaluationCase(task="cross-episode digest", references=refs)
        except ImportError:
            case = None

        def _digest_agent(command, context, job):
            for ep in episodes:
                job.add_step("observation", f"{ep.show}: {ep.title}")
            for ins in digest.insights:
                job.add_step("action", f"insight: {ins.claim}")
            return final

        result = run_job("podcast cross-episode digest", _digest_agent,
                         profile="researcher", memory=self.memory, skills=self.skills,
                         recorder=self.recorder, jobs=self.jobs, case=case)
        reasoner_note = "LLM reasoner" if self.reasoner else "deterministic fallback"
        return (digest.render()
                + f"\n\n[{reasoner_note}] {result.verdict} · score {result.ninja_score:.1f}"
                + f" · Job {result.job_id[-8:]} (try /trace {result.job_id[-8:]})")

    # --- Level 3: controlled autonomy --------------------------------------

    def _profile_for(self, level: str) -> str:
        # Read-only → researcher; anything that writes/sends/deploys → operator.
        return "researcher" if level == "READ_ONLY" else "operator"

    def _execute(self, task: str, profile: str) -> str:
        from agent_os.runner import run_job

        result = run_job(task, self.agent_fn, profile=profile, memory=self.memory,
                         skills=self.skills, recorder=self.recorder, jobs=self.jobs)
        return result, result.summary + f"\n\nJob: {result.job_id[-8:]}"

    def _run(self, args: list[str]) -> str:
        from agent_os.risk import classify_risk

        task = " ".join(args).strip()
        if not task:
            return "Usage: /run <task>"
        assessment = classify_risk(task)
        label = "AMBIGUOUS" if assessment.ambiguous else assessment.level.label
        if not assessment.requires_approval:
            result, summary = self._execute(task, self._profile_for("READ_ONLY"))
            return f"[risk: READ_ONLY → auto-run]\n{summary}\n{self._meter_line(result)}"
        approval_id = self.approvals.enqueue(
            task, self._profile_for(assessment.level.label), label, assessment.reason,
        )
        return (
            f"⛔ Needs approval — risk: {label} ({assessment.reason}).\n"
            f"Task: {task}\n"
            f"Approve:  /approve {approval_id}\n"
            f"Reject:   /reject {approval_id}"
        )

    def _swarm(self, args: list[str]) -> str:
        """Governed swarm: decompose the goal, run sub-tasks in parallel (each a
        traced, risk-gated, scored job), then synthesize one deliverable."""
        from agent_os.orchestrator import Orchestrator

        goal = " ".join(args).strip()
        if not goal:
            return ("Usage: /swarm <goal>\n"
                    "Decomposes the goal, runs read-only sub-tasks in parallel "
                    "(each traced + scored), gates anything privileged, then "
                    "synthesizes one deliverable. Set AGENT_OS_PROVIDER for real "
                    "decomposition/synthesis (Ollama works).")
        orch = Orchestrator(
            provider=self.provider, skills=self.skills,
            state_dir=str(self.memory.root), traces_dir=str(self.recorder.root),
            jobs_db=str(self.jobs.db_path), audit=self.audit,
        )
        return orch.run(goal).render()

    def _risk(self, args: list[str]) -> str:
        from agent_os.risk import classify_risk

        task = " ".join(args).strip()
        if not task:
            return "Usage: /risk <task>"
        a = classify_risk(task)
        gate = "auto-run" if not a.requires_approval else "REQUIRES APPROVAL"
        return f"Risk: {a.level.label} → {gate}\nReason: {a.reason}"

    def _pending(self) -> str:
        items = self.approvals.list(status="pending")
        if not items:
            return "No actions awaiting approval. ✅"
        lines = ["Pending approvals:"]
        for a in items:
            lines.append(f"  {a['id']}  [{a['risk_level']}]  {a['command'][:50]}")
            lines.append(f"      /approve {a['id']}   /reject {a['id']}")
        return "\n".join(lines)

    def _approve(self, args: list[str]) -> str:
        if not args:
            return "Usage: /approve <id>"
        rec = self.approvals.get(args[0])
        if not rec:
            return f"No approval found matching '{args[0]}'."
        if rec["status"] != "pending":
            return f"Approval {rec['id']} is already {rec['status']}."
        result, summary = self._execute(rec["command"], rec["profile"])
        self.approvals.set_decision(rec["id"], "approved", job_id=result.job_id)
        return f"✅ Approved & executed [{rec['risk_level']}].\n{summary}"

    def _reject(self, args: list[str]) -> str:
        if not args:
            return "Usage: /reject <id>"
        rec = self.approvals.get(args[0])
        if not rec:
            return f"No approval found matching '{args[0]}'."
        if rec["status"] != "pending":
            return f"Approval {rec['id']} is already {rec['status']}."
        self.approvals.set_decision(rec["id"], "rejected")
        return f"🚫 Rejected approval {rec['id']}. No action taken."

    def _job(self, args: list[str]) -> str:
        if not args:
            return "Usage: /job <id>"
        job = self.jobs.find(args[0])
        if not job:
            return f"No job found matching '{args[0]}'."
        return (
            f"Job {job['job_id']}\n"
            f"  command : {job['command']}\n"
            f"  profile : {job['profile']}   skill: {job['skill'] or '-'}\n"
            f"  status  : {job['status']}\n"
            f"  verdict : {job.get('verdict') or '-'}   "
            f"score: {(job.get('ninja_score') or 0):.1f}   "
            f"cert: {job.get('certification') or '-'}\n"
            f"  flagged : {bool(job.get('flagged'))}\n"
            f"  trace   : {job.get('trace_path') or '-'}\n"
            f"  report  : {job.get('report_path') or '-'}\n"
            f"  created : {job['created_at']}"
        )

    def _trace(self, args: list[str]) -> str:
        if not args:
            return "Usage: /trace <id>"
        job = self.jobs.find(args[0])
        if not job:
            return f"No job found matching '{args[0]}'."
        trace_path = job.get("trace_path")
        if not trace_path or not Path(trace_path).exists():
            return f"Job {job['job_id'][-8:]} has no saved trace."
        trace = json.loads(Path(trace_path).read_text())
        steps = trace.get("steps", [])
        tools = trace.get("tool_calls", [])
        final = (trace.get("final_output") or "").strip()
        lines = [
            f"Trace {job['job_id'][-8:]}  [{trace.get('agent_name')}]",
            f"  task   : {trace.get('task', '')[:60]}",
            f"  steps  : {len(steps)}   tools: {len(tools)}",
        ]
        for s in steps[:6]:
            lines.append(f"    - {s.get('step_type')}: {(s.get('output') or '')[:48]}")
        if tools:
            lines.append("  tool calls:")
            for t in tools[:6]:
                lines.append(f"    - {t.get('tool_name')} [{t.get('status')}]")
        if job.get("ninja_score") is not None:
            lines.append(f"  score  : {job['ninja_score']:.1f}  ({job.get('verdict') or job.get('certification')})")
        lines.append(f"  final  : {final[:160]}")
        return "\n".join(lines)

    def close(self) -> None:
        self.jobs.close()
        self.memory.close()
        self.approvals.close()
        self.audit.close()
        self.context.close()
