"""
agent-os CLI (standard-library argparse — no heavy deps of its own).

    agent-os run "summarize the BISAD inbox" --profile operator
    agent-os run "research X" --agent-cmd "python my_agent.py" --case case.yaml
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
from agent_os.runner import run_job
from agent_os.skill_registry import SkillRegistry
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
    skills = SkillRegistry(args.skills_dir)
    recorder = TraceRecorder(args.traces_dir)
    agent_fn = _command_agent(shlex.split(args.agent_cmd)) if args.agent_cmd else _demo_agent

    result = run_job(
        args.command, agent_fn,
        profile=args.profile, memory=memory, skills=skills, recorder=recorder,
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
    # Non-zero exit unless it's a clean PASS at/above the profile threshold (CI gate).
    return 0 if (result.verdict == "PASS" and not result.flagged) else 2


def _cmd_skills(args: argparse.Namespace) -> int:
    reg = SkillRegistry(args.skills_dir)
    skills = reg.all()
    if not skills:
        print(f"No skills found in {args.skills_dir}/")
        return 0
    for s in skills:
        print(f"- {s.name}: {s.description}")
        print(f"    triggers: {', '.join(s.triggers)}")
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
