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
import re
import subprocess
import threading
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
                 audit=None, context=None, provider=None, policy=None, hooks=None,
                 mcp_registry=None) -> None:
        from agent_os.approvals import ApprovalStore
        from agent_os.audit import AuditLog
        from agent_os.context import ContextStore
        from agent_os.risk import classify_risk

        self.jobs = jobs or JobStore()
        self.memory = memory or AgentMemory()
        self.skills = skills or SkillRegistry()
        self.recorder = recorder or TraceRecorder()
        self.approvals = approvals or ApprovalStore(Path(self.memory.root) / "approvals.db")
        self.audit = audit or AuditLog(Path(self.memory.root) / "audit.db")
        self.context = context or ContextStore(Path(self.memory.root) / "context.db")
        self.agent_fn = agent_fn or _default_agent
        # Pluggable risk policy: any callable(command, tools=None) -> RiskAssessment.
        # Defaults to the built-in default-deny classifier; swap it to enforce your
        # own org policy without forking the router. The gate still runs every time.
        self.policy = policy or classify_risk
        # Composable hooks (redaction et al.) threaded into every run_job call.
        # None → run_job uses HookRegistry.default() (redaction on).
        self.hooks = hooks
        # MCP connector bridge (Module 4): your own servers, declared in
        # ~/.agent-os/mcp.json — agent-os bundles none and stores no credentials.
        # Built lazily on first use so importing the router costs nothing; every
        # call still flows through the risk gate + audit log + eval, below.
        self._mcp_registry = mcp_registry
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
        # Background onboarding (the UI's "Pull recommended model" button). The
        # model pull can be many GB / minutes, so it runs in a daemon thread and
        # the UI polls onboarding_status() for live progress — never a blocking
        # request. Guarded by a lock; the HTTP server stays single-threaded.
        self._onboard_lock = threading.Lock()
        self._onboard_thread: threading.Thread | None = None
        self._onboard: dict = {
            "state": "idle", "phase": "", "pct": None, "lines": [], "model": None,
            "verified": False, "persisted": False, "provider": None, "error": None,
        }

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
            "recall": self._recall,
            "audit": lambda a: self._audit(),
            "model": lambda a: self._model(),
            "doctor": lambda a: self._doctor(),
            "setup": lambda a: self._setup(),
            "cost": lambda a: self._cost(),
            "job": self._job,
            "trace": self._trace,
            "run": self._run,
            "swarm": self._swarm,
            "mcp": lambda a: self._mcp(),
            "mcp-tools": self._mcp_tools,
            "mcp-call": self._mcp_call,
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
            "  /recall <query>  search your past sessions (cross-session memory)\n"
            "  /audit           recent audit entries + chain integrity\n"
            "  /model           show the configured model provider\n"
            "  /doctor          detect hardware + recommend a local model\n"
            "  /setup           guided setup steps to a working local model\n"
            "  /cost            cost · latency · token usage across recent runs\n"
            "  /job <id>        show a job record\n"
            "  /trace <id>      show a job's trace summary\n"
            "  /run <task>      submit a task (auto-runs if read-only; else needs approval)\n"
            "  /swarm <goal>    governed swarm: decompose → parallel sub-jobs → synthesize\n"
            "  /mcp             list your configured MCP connector servers\n"
            "  /mcp-tools <srv> list a server's tools (with each tool's risk gate)\n"
            "  /mcp-call <srv> <tool> [json]  call an MCP tool (gated · traced · scored)\n"
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
                         jobs=self.jobs, case=case, hooks=self.hooks)
        g = result.result.metric_by_name("grounding") if result.result else None
        gtxt = f" · grounding {g.score:.2f}" if g and g.is_applicable else ""
        return f"{holder['answer']}\n\n[{result.verdict}{gtxt} · Job {result.job_id[-8:]}]"

    def _recall(self, args: list[str]) -> str:
        """Cross-session memory: full-text search over your past sessions. Returns
        the ranked hits (deterministic), and — if a model is configured — a short
        synthesis of what was done about this topic. Read-only; nothing executes."""
        if not args:
            return "Usage: /recall <query>   (searches your previous /run, /ask, /swarm …)"
        query = " ".join(args)
        hits = self.memory.search_sessions(query, limit=8)
        if not hits:
            return (f"No past sessions match '{query}'. "
                    "Recall searches what you've already done (/run, /ask, /swarm …).")
        lines = [f"🔎 {len(hits)} past session(s) about '{query}':", ""]
        for h in hits:
            day = (h.get("ts") or "")[:10]
            cmd = (h.get("command") or "").strip()[:64]
            snip = (h.get("snippet") or "").strip()
            lines.append(f"  • {day}  {cmd}  (job {h.get('job_id', '')[-8:]})")
            if snip:
                lines.append(f"        …{snip}…")
        listing = "\n".join(lines)

        if self.provider is None:
            return listing
        try:
            evidence = "\n".join(
                f"- [{(h.get('ts') or '')[:10]}] {h.get('command', '')}: "
                f"{(h.get('snippet') or '').strip()}"
                for h in hits
            )
            synthesis = self.provider.complete(
                f"The user asks to recall: {query}\n\n"
                f"Here are excerpts from their past sessions:\n{evidence}\n\n"
                "In 2–4 sentences, summarize what they did about this and any "
                "useful takeaway. Use ONLY the excerpts; if they don't cover it, say so.",
                system="You summarize a user's own past activity faithfully and concisely.",
            ).strip()
        except Exception:  # noqa: BLE001 - synthesis is a bonus; never break recall
            return listing
        return f"{synthesis}\n\n{listing}" if synthesis else listing

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

    def _setup(self) -> str:
        """Read-only guided setup: the exact steps to a working local model.
        The chat/`/setup` surface never executes — it only explains. Execution is
        an explicit user action: `agent-os setup --run` (CLI) or the 'Pull model'
        button in the local UI, which call `run_onboarding()` below."""
        from agent_os import onboarding

        text = onboarding.guidance()
        if self.provider is None:
            return text
        return (f"Model already configured: {self.provider.name} ✅\n\n" + text)

    def run_onboarding(self, model: str | None = None) -> dict:
        """Execute guided setup — pull the recommended model + persist the choice —
        and re-bind the live provider so the UI works without a restart.

        This is the one execution path outside the CLI, and it is reached ONLY by
        an explicit user action (the local UI's 'Pull model' button = a human
        approving their own setup). It is a local, reversible, no-secret action,
        not an agent task — so it sits beside the default-deny gate, not under it.
        It still NEVER installs the Ollama binary itself; if Ollama is missing the
        returned steps say so and nothing is pulled. Read-only surfaces (chat,
        `/setup`) never reach here."""
        from agent_os import onboarding

        lines: list[str] = []
        res = onboarding.run_setup(execute=True, model=model, writer=lines.append)
        if res.persisted_to:                       # re-bind so /ask + /run go smart now
            try:
                from agent_os.providers import provider_from_env
                self.provider = provider_from_env()
                if self.provider is not None:
                    self.agent_fn = self.provider.as_agent_fn()
                    self.reasoner = self.provider.as_reasoner()
                    try:
                        self.context.embedder = self.provider.as_embedder()
                        self.context.reindex_embeddings()
                    except Exception:  # noqa: BLE001 - embeddings optional
                        pass
            except Exception:  # noqa: BLE001 - a bad spec must not break the UI
                pass
        self.audit.record(f"/setup --run {model or ''}".strip(), actor="webui",
                          decision="verified" if res.verified else "setup-run")
        return {
            "output": "\n".join(lines),
            "verified": res.verified,
            "persisted": bool(res.persisted_to),
            "model_present": res.model_present,
            "ollama_installed": res.ollama_installed,
            "ollama_running": res.ollama_running,
            "steps": res.steps,
            "provider": self.provider.name if self.provider else None,
        }

    # --- background onboarding (live progress for the UI) -------------------

    @staticmethod
    def _stream_shell(cmd: list[str], writer) -> int:
        """Run a command, streaming output as it arrives. Unlike a line-buffered
        read, this splits on both '\\n' and '\\r' so `ollama pull`'s in-place
        progress updates (which use carriage returns) surface live, line by line."""
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            writer(f"(command not found: {cmd[0]})")
            return 127
        assert proc.stdout is not None
        buf = ""
        while True:
            chunk = proc.stdout.read(80)
            if not chunk:
                break
            buf += chunk
            while True:
                idx = min((buf.find(c) for c in "\r\n" if c in buf), default=-1)
                if idx < 0:
                    break
                line, buf = buf[:idx], buf[idx + 1:]
                if line.strip():
                    writer(line.strip())
        if buf.strip():
            writer(buf.strip())
        return proc.wait()

    def onboarding_plan(self) -> dict:
        """A cheap, read-only preview of what one-click setup will do: which model
        gets enabled, whether it's already downloaded (instant) or needs a pull,
        and any optional upgrade. Lets the UI label the button honestly. Read-only
        — diagnoses hardware/Ollama, changes nothing."""
        from agent_os import doctor

        d = doctor.diagnose()
        pick = doctor.smart_pick(d)
        return {
            "model": pick.model,
            "already_present": pick.already_present,
            "upgrade": pick.upgrade,
            "ollama_installed": d.ollama_installed,
            "ollama_running": d.ollama_running,
            "configured": self.provider is not None,
        }

    def onboarding_status(self) -> dict:
        """A thread-safe snapshot of the background setup job, for UI polling."""
        with self._onboard_lock:
            snap = dict(self._onboard)
            snap["lines"] = list(self._onboard["lines"])[-12:]
            snap["done"] = snap["state"] in ("done", "error")
            snap["running"] = snap["state"] == "running"
            return snap

    def start_onboarding(self, model: str | None = None) -> dict:
        """Kick off the model pull + enable in a background thread and return
        immediately. The UI polls onboarding_status() to render live progress.

        Same governance as run_onboarding(): an explicit user button-click (human
        approval of their own local setup), audited, never installs Ollama itself.
        Idempotent — a second click while running just returns the live status."""
        with self._onboard_lock:
            if self._onboard["state"] == "running":
                snap = dict(self._onboard)
                snap["lines"] = list(self._onboard["lines"])[-12:]
                snap["done"] = False
                snap["running"] = True
                return snap
            self._onboard = {
                "state": "running", "phase": "Checking your machine…", "pct": None,
                "lines": [], "model": model, "verified": False, "persisted": False,
                "provider": None, "error": None,
            }
        # Audit the intent from the serving thread (keeps SQLite single-threaded).
        try:
            self.audit.record(f"/setup --run {model or ''}".strip(), actor="webui",
                              decision="setup-start")
        except Exception:  # noqa: BLE001 - auditing must not block setup
            pass
        # Snapshot the just-set running state BEFORE starting the worker, so the
        # return value always (and accurately) reports "running" — the call has
        # started the job. Snapshotting after t.start() would race a fast worker
        # that finishes before we read back, making the POST look already "done".
        snap = self.onboarding_status()
        t = threading.Thread(target=self._onboard_worker, args=(model,), daemon=True)
        self._onboard_thread = t
        t.start()
        return snap

    def _onboard_set(self, **kw) -> None:
        with self._onboard_lock:
            self._onboard.update(kw)

    def _onboard_write(self, line: str) -> None:
        """Writer for the background pull: append the log line and derive a
        human-readable phase + percentage so the UI can show a real progress bar."""
        with self._onboard_lock:
            self._onboard["lines"].append(line)
            m = re.search(r"(\d{1,3})%", line)
            if m:
                self._onboard["pct"] = max(0, min(100, int(m.group(1))))
            low = line.lower()
            if line.startswith("②") or "pulling" in low or "downloading" in low:
                self._onboard["phase"] = "Downloading the model…"
            elif line.startswith("③") or "saved your choice" in low:
                self._onboard["phase"] = "Enabling it…"
            elif line.startswith("④") or "verifying" in low or "model says" in low:
                self._onboard["phase"] = "Verifying…"

    def _onboard_worker(self, model: str | None) -> None:
        from agent_os import onboarding

        try:
            res = onboarding.run_setup(
                execute=True, model=model, writer=self._onboard_write,
                shell=self._stream_shell,
            )
            if res.persisted_to:                    # re-bind so /ask + /run go smart now
                try:
                    from agent_os.providers import provider_from_env
                    self.provider = provider_from_env()
                    if self.provider is not None:
                        self.agent_fn = self.provider.as_agent_fn()
                        self.reasoner = self.provider.as_reasoner()
                        try:
                            self.context.embedder = self.provider.as_embedder()
                            self.context.reindex_embeddings()
                        except Exception:  # noqa: BLE001 - embeddings optional / cross-thread
                            pass
                except Exception:  # noqa: BLE001 - a bad spec must not break the UI
                    pass
            ready = bool(res.verified or (res.model_present and res.persisted_to))
            self._onboard_set(
                state="done",
                phase="Ready" if ready else "Setup didn't finish",
                pct=100 if res.model_present else self._onboard.get("pct"),
                verified=res.verified, persisted=bool(res.persisted_to),
                model_present=res.model_present, model=res.recommended,
                provider=self.provider.name if self.provider else None,
                ollama_installed=res.ollama_installed,
            )
        except Exception as exc:  # noqa: BLE001 - surface, never crash the UI thread
            self._onboard_set(state="error", phase="Something went wrong",
                              error=f"{type(exc).__name__}: {exc}")

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
                         skills=self.skills, recorder=self.recorder, jobs=self.jobs,
                         hooks=self.hooks)
        return result, result.summary + f"\n\nJob: {result.job_id[-8:]}"

    def _run(self, args: list[str]) -> str:
        task = " ".join(args).strip()
        if not task:
            return "Usage: /run <task>"
        assessment = self.policy(task)
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

    # --- Module 4: MCP connector bridge ------------------------------------

    def _mcp_reg(self):
        """Lazily build the MCP registry from the user's ~/.agent-os/mcp.json.
        Bundles nothing; if the file is absent the registry is simply empty."""
        if self._mcp_registry is None:
            from agent_os.mcp import MCPRegistry
            self._mcp_registry = MCPRegistry()
        return self._mcp_registry

    def _mcp(self) -> str:
        """List the MCP servers the user has declared (read-only)."""
        reg = self._mcp_reg()
        names = reg.names()
        if not names:
            return (
                "No MCP servers configured.\n"
                f"Declare your own in {reg.path} — agent-os bundles none and stores "
                "no credentials:\n"
                '  {"servers": {"filesystem": {"command": ["npx","-y",'
                '"@modelcontextprotocol/server-filesystem","/path"]}}}\n\n'
                "Then: /mcp-tools <server> to list tools · "
                "/mcp-call <server> <tool> {json} to call one (gated)."
            )
        lines = ["MCP servers (yours — declared in mcp.json):"]
        for n in names:
            cfg = reg.get(n)
            argv = " ".join(cfg.command) if cfg else ""
            lines.append(f"  {n} — {argv[:64]}")
        lines.append("\n/mcp-tools <server> · /mcp-call <server> <tool> {json-args}")
        return "\n".join(lines)

    def _mcp_tools(self, args: list[str]) -> str:
        """List a server's tools, each tagged with the risk gate it would hit."""
        if not args:
            return "Usage: /mcp-tools <server>"
        name = args[0]
        reg = self._mcp_reg()
        if not reg.get(name):
            return f"No MCP server '{name}'. Try /mcp to list configured servers."
        from agent_os.mcp import MCPError

        try:
            tools = reg.list_tools(name)
        except MCPError as exc:
            return f"⚠️ Could not list tools from '{name}': {exc}"
        if not tools:
            return f"'{name}' exposes no tools."
        lines = [f"Tools on '{name}' (risk gate previewed per tool):"]
        for t in tools:
            tname = str(t.get("name", "?"))
            a = self.policy(f"mcp {tname}", tools=[tname])
            gate = "auto-run" if not a.requires_approval else "needs approval"
            label = "AMBIGUOUS" if a.ambiguous else a.level.label
            desc = (t.get("description") or "").strip().splitlines()
            tip = f" — {desc[0][:60]}" if desc else ""
            lines.append(f"  {tname}  [{label} → {gate}]{tip}")
        lines.append("\nCall one: /mcp-call " + name + " <tool> {json-args}")
        return "\n".join(lines)

    def _mcp_call(self, args: list[str]) -> str:
        """Call an MCP tool through the spine: risk-gated (default-deny), and on
        auto-run executed via run_job so it's traced + scored + persisted. A
        write/send/deploy (or ambiguous) tool is enqueued for /approve instead."""
        if len(args) < 2:
            return "Usage: /mcp-call <server> <tool> [json-args]"
        server, tool = args[0], args[1]
        raw = " ".join(args[2:]).strip()
        try:
            arguments = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            return f"⚠️ Invalid JSON args: {exc}. Example: /mcp-call {server} {tool} {{\"path\":\"/tmp\"}}"
        if not isinstance(arguments, dict):
            return "⚠️ Tool args must be a JSON object, e.g. {\"path\": \"/tmp\"}."
        reg = self._mcp_reg()
        if not reg.get(server):
            return f"No MCP server '{server}'. Try /mcp to list configured servers."

        assessment = self.policy(f"mcp {tool}", tools=[tool])
        label = "AMBIGUOUS" if assessment.ambiguous else assessment.level.label
        if not assessment.requires_approval:
            result, summary = self._mcp_execute(server, tool, arguments)
            return f"[risk: {label} → auto-run]\n{summary}\n{self._meter_line(result)}"
        approval_id = self.approvals.enqueue(
            f"/mcp-call {server} {tool} {json.dumps(arguments)}",
            "operator", label, assessment.reason,
        )
        return (
            f"⛔ Needs approval — MCP {label} ({assessment.reason}).\n"
            f"Server: {server}   Tool: {tool}\n"
            f"Approve:  /approve {approval_id}\n"
            f"Reject:   /reject {approval_id}"
        )

    def _mcp_execute(self, server: str, tool: str, arguments: dict):
        """Run one MCP tool call inside a traced/scored/persisted job. Returns
        (JobResult, reply) where the reply shows the tool's actual output (the
        point of the call) plus the verdict and job id for follow-up."""
        from agent_os.runner import run_job

        reg = self._mcp_reg()
        holder: dict[str, str] = {}

        def _mcp_agent(command, context, job):
            job.add_step("plan", f"Call MCP tool '{tool}' on server '{server}'.")
            out = reg.call(server, tool, arguments)
            job.add_tool_call(f"mcp:{server}:{tool}", arguments,
                              result=(out or "")[:300], status="success")
            job.add_step("observation", f"Tool returned {len(out or '')} char(s).")
            holder["out"] = out or "(no output)"
            return holder["out"]

        result = run_job(f"mcp call {server}/{tool}", _mcp_agent, profile="operator",
                         memory=self.memory, skills=self.skills, recorder=self.recorder,
                         jobs=self.jobs, hooks=self.hooks)
        reply = (f"🔌 {server}/{tool} →\n{holder.get('out', '(no output)')}\n\n"
                 f"[{result.verdict} · score {result.ninja_score:.1f} · "
                 f"Job {result.job_id[-8:]}]")
        return result, reply

    def _dispatch_mcp_command(self, command: str):
        """Re-run a stored '/mcp-call <server> <tool> <json>' approval command."""
        parts = command.split(maxsplit=3)
        server, tool = parts[1], parts[2]
        arguments = json.loads(parts[3]) if len(parts) > 3 else {}
        return self._mcp_execute(server, tool, arguments)

    def _risk(self, args: list[str]) -> str:
        task = " ".join(args).strip()
        if not task:
            return "Usage: /risk <task>"
        a = self.policy(task)
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
        if rec["command"].startswith("/mcp-call "):
            result, summary = self._dispatch_mcp_command(rec["command"])
        else:
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
