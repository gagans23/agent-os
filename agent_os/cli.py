"""
agent-os CLI (standard-library argparse — no heavy deps of its own).

    agent-os run "summarize the BISAD inbox" --profile operator
    agent-os run "research X" --agent-cmd "python my_agent.py" --case case.yaml
    agent-os cmd "/status"          # the WhatsApp-style command surface
    agent-os cmd "/job f6df6f7d"
    agent-os skills
    agent-os memory
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys

from agent_os.agent_memory import AgentMemory
from agent_os.command_router import CommandRouter
from agent_os.jobs import JobStore
from agent_os.runner import run_job
from agent_os.skill_registry import SkillRegistry, skill_roots_from_env
from agent_os.trace_recorder import JobRecorder, TraceRecorder


def _demo_agent(command: str, context: str, job: JobRecorder) -> str:
    """A trivial built-in agent so `agent-os run` works out of the box."""
    job.add_step("plan", f"Plan a response to: {command[:80]}")
    job.add_step("action", "Composed a concise answer (demo agent).")
    return f"Done: {command}. (Replace this with your real agent via --agent-cmd.)"


def _command_agent(cmd: list[str]):
    """Wrap an external agent: it receives the command on stdin and prints the
    final answer on stdout. Steps/tools can be added by parsing its output; here
    we record stdout as the final answer and log stderr."""
    def agent_fn(command: str, context: str, job: JobRecorder) -> str:
        job.add_step("action", f"Running external agent: {' '.join(cmd)}")
        proc = subprocess.run(cmd, input=command, capture_output=True, text=True, timeout=300)
        if proc.stderr:
            job.log(proc.stderr)
        if proc.returncode != 0:
            job.add_step("action", "External agent exited non-zero", status="failed",
                         error=proc.stderr[:300])
        return proc.stdout.strip() or "(agent produced no output)"
    return agent_fn


def _cmd_run(args: argparse.Namespace) -> int:
    memory = AgentMemory(args.state_dir)
    skills = SkillRegistry(skill_roots_from_env(args.skills_dir))
    recorder = TraceRecorder(args.traces_dir)
    jobs = JobStore(f"{args.state_dir}/jobs.db")
    agent_fn = _command_agent(shlex.split(args.agent_cmd)) if args.agent_cmd else _demo_agent

    result = run_job(
        args.command, agent_fn,
        profile=args.profile, memory=memory, skills=skills, recorder=recorder, jobs=jobs,
        case_path=args.case, evaluate=not args.no_eval,
    )
    if args.json:
        print(json.dumps({
            "job_id": result.job_id,
            "certification": result.certification,
            "ninja_score": result.ninja_score,
            "skill": result.skill.name if result.skill else None,
            "trace_path": result.trace_path,
            "report_path": result.report_path,
            "proposal": result.proposal.to_dict() if result.proposal else None,
        }, indent=2))
    else:
        print(result.summary)
        if result.proposal:
            print("\n--- Improvement proposal (requires your approval) ---")
            print("Reason :", "; ".join(result.proposal.reasons) or "(see report)")
            print("Memory :", result.proposal.memory_suggestion)
            print("Skill  :", result.proposal.skill_patch_suggestion)
    memory.close()
    jobs.close()
    # Non-zero exit unless it's a clean PASS at/above the profile threshold (CI gate).
    return 0 if (result.verdict == "PASS" and not result.flagged) else 2


def _cmd_health(args: argparse.Namespace) -> int:
    from agent_os.health import run_health_checks

    report = run_health_checks(args.state_dir, args.skills_dir, args.traces_dir)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())
    return 0 if report.status != "down" else 1


def _cmd_supervise(args: argparse.Namespace) -> int:
    from agent_os.logging_setup import configure
    from agent_os.supervisor import Supervisor, SupervisorPolicy

    configure(logfile=args.logfile)
    policy = SupervisorPolicy(max_restarts=args.max_restarts)
    Supervisor(args.command, policy).run()
    return 0


def _cmd_daily_eval(args: argparse.Namespace) -> int:
    from agent_os.daily_eval import daily_summary

    print(daily_summary(state_dir=args.state_dir, suite_path=args.suite))
    return 0


def _cmd_router(args: argparse.Namespace) -> int:
    """Dispatch a WhatsApp-style command via the CommandRouter."""
    router = CommandRouter(
        jobs=JobStore(f"{args.state_dir}/jobs.db"),
        memory=AgentMemory(args.state_dir),
        skills=SkillRegistry(skill_roots_from_env(args.skills_dir)),
        recorder=TraceRecorder(args.traces_dir),
        suite_path=args.suite,
    )
    text = " ".join(args.text)
    print(router.handle(text))
    router.close()
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    """Launch the local web UI (the 'click a button' surface)."""
    from agent_os.webui import serve

    serve(host=args.host, port=args.port, state_dir=args.state_dir,
          skills_dir=args.skills_dir, traces_dir=args.traces_dir, suite=args.suite,
          open_browser=not args.no_browser)
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Detect hardware and recommend a local model."""
    from agent_os.doctor import diagnose, render

    print(render(diagnose()))
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    """Guided 'click a button' setup. Without --run it only explains + prints
    commands (changes nothing). With --run it pulls the model and remembers your
    provider choice — but never installs Ollama itself (that stays your call)."""
    from agent_os import onboarding

    res = onboarding.run_setup(execute=args.run, model=args.model)
    return 0 if (not args.run or res.verified or res.model_present
                 or "ollama-install-needed" in res.steps) else 2


def _cmd_swarm(args: argparse.Namespace) -> int:
    """Run a goal as a governed parallel swarm (decompose → parallel → synthesize)."""
    from agent_os.orchestrator import Orchestrator
    from agent_os.providers import provider_from_env

    orch = Orchestrator(
        provider=provider_from_env(),
        skills=SkillRegistry(skill_roots_from_env(args.skills_dir)),
        state_dir=args.state_dir, traces_dir=args.traces_dir,
        jobs_db=f"{args.state_dir}/jobs.db", concurrency=args.concurrency,
    )
    print(orch.run(args.goal, n=args.subtasks).render())
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    reg = SkillRegistry(skill_roots_from_env(args.skills_dir))
    skills = reg.all()
    if not skills:
        print(f"No skills found in {args.skills_dir}/")
        return 0
    print(f"{len(skills)} skill(s) across {len(reg.roots)} root(s):")
    for s in skills:
        print(f"- {s.name}: {s.description}")
        print(f"    triggers: {', '.join(s.triggers)}")
        if s.allowed_tools:
            print(f"    allowed-tools: {', '.join(s.allowed_tools)}")
    return 0


def _cmd_memory(args: argparse.Namespace) -> int:
    memory = AgentMemory(args.state_dir)
    outcomes = memory.recent_outcomes(limit=args.limit)
    if not outcomes:
        print("No recorded outcomes yet.")
    for o in outcomes:
        print(f"{o['created_at']}  {o['certification']:<5} {o['score']:>5.1f}  "
              f"[{o['profile']}/{o['skill'] or '-'}]  {o['task'][:60]}")
    memory.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-os", description="Self-improving agent platform (Ninja Harness eval gate).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a command end-to-end (trace → eval → propose).")
    p_run.add_argument("command")
    p_run.add_argument("--profile", default="researcher")
    p_run.add_argument("--agent-cmd", default=None, help="External agent command (stdin→stdout).")
    p_run.add_argument("--case", default=None, help="Eval case YAML/JSON path.")
    p_run.add_argument("--skills-dir", default="skills")
    p_run.add_argument("--state-dir", default="agent_state")
    p_run.add_argument("--traces-dir", default="traces")
    p_run.add_argument("--no-eval", action="store_true")
    p_run.add_argument("--json", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_sk = sub.add_parser("skills", help="List available skills.")
    p_sk.add_argument("--skills-dir", default="skills")
    p_sk.set_defaults(func=_cmd_skills)

    p_mem = sub.add_parser("memory", help="Show recent job outcomes.")
    p_mem.add_argument("--state-dir", default="agent_state")
    p_mem.add_argument("--limit", type=int, default=10)
    p_mem.set_defaults(func=_cmd_memory)

    p_cmd = sub.add_parser("cmd", help="Dispatch a WhatsApp-style command (/status, /job <id>, ...).")
    p_cmd.add_argument("text", nargs="+", help="The command, e.g. '/job f6df6f7d'.")
    p_cmd.add_argument("--state-dir", default="agent_state")
    p_cmd.add_argument("--skills-dir", default="skills")
    p_cmd.add_argument("--traces-dir", default="traces")
    p_cmd.add_argument("--suite", default=None, help="Ninja Harness suite path for /eval.")
    p_cmd.set_defaults(func=_cmd_router)

    p_doc = sub.add_parser("doctor", help="Detect hardware + recommend a local model.")
    p_doc.set_defaults(func=_cmd_doctor)

    p_set = sub.add_parser("setup", help="Guided setup to a working local model (click-a-button flow).")
    p_set.add_argument("--run", action="store_true",
                       help="Also pull the model + remember your provider choice "
                            "(never installs Ollama itself).")
    p_set.add_argument("--model", default=None, help="Override the recommended model tag.")
    p_set.set_defaults(func=_cmd_setup)

    p_sw = sub.add_parser("swarm", help="Run a goal as a governed parallel swarm.")
    p_sw.add_argument("goal")
    p_sw.add_argument("--concurrency", type=int, default=4,
                      help="Max sub-tasks running at once (size to your machine/provider).")
    p_sw.add_argument("--subtasks", type=int, default=None,
                      help="Target number of sub-tasks for model decomposition.")
    p_sw.add_argument("--skills-dir", default="skills")
    p_sw.add_argument("--state-dir", default="agent_state")
    p_sw.add_argument("--traces-dir", default="traces")
    p_sw.set_defaults(func=_cmd_swarm)

    p_ui = sub.add_parser("ui", help="Launch the local web UI (click a button).")
    p_ui.add_argument("--host", default="127.0.0.1", help="Bind address (localhost by default).")
    p_ui.add_argument("--port", type=int, default=8765)
    p_ui.add_argument("--state-dir", default="agent_state")
    p_ui.add_argument("--skills-dir", default="skills")
    p_ui.add_argument("--traces-dir", default="traces")
    p_ui.add_argument("--suite", default=None, help="Ninja Harness suite path for /eval.")
    p_ui.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser.")
    p_ui.set_defaults(func=_cmd_ui)

    p_hp = sub.add_parser("health", help="Run health checks.")
    p_hp.add_argument("--state-dir", default="agent_state")
    p_hp.add_argument("--skills-dir", default="skills")
    p_hp.add_argument("--traces-dir", default="traces")
    p_hp.add_argument("--json", action="store_true")
    p_hp.set_defaults(func=_cmd_health)

    p_sup = sub.add_parser("supervise", help="Keep a bridge/agent process alive (restart on crash).")
    p_sup.add_argument("command", nargs="+", help="The process command, e.g. python bridge.py")
    p_sup.add_argument("--max-restarts", type=int, default=10)
    p_sup.add_argument("--logfile", default=None)
    p_sup.set_defaults(func=_cmd_supervise)

    p_de = sub.add_parser("daily-eval", help="Print a daily reliability summary.")
    p_de.add_argument("--state-dir", default="agent_state")
    p_de.add_argument("--suite", default=None)
    p_de.set_defaults(func=_cmd_daily_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
