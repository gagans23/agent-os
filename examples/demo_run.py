#!/usr/bin/env python3
"""
Runnable demo of the agent-os loop: command → trace → Ninja Harness eval →
improvement proposal → WhatsApp-style summary. No external services.

    python examples/demo_run.py
"""

from __future__ import annotations

from agent_os import AgentMemory, SkillRegistry, TraceRecorder, run_job
from agent_os.trace_recorder import JobRecorder


def browser_research_agent(command: str, context: str, job: JobRecorder) -> str:
    """A tiny deterministic 'researcher' that records a clean trajectory."""
    job.add_step("plan", "Open Hacker News and extract the top stories.")
    job.add_tool_call("browser_open", {"url": "https://news.ycombinator.com"},
                      result="ok", status="success")
    job.add_tool_call("save_artifact", {"name": "report.md"}, result="saved", status="success")
    job.add_screenshot("home.txt", data=b"(screenshot placeholder)")
    return (
        "Browser demo completed: opened Hacker News, extracted the top stories, "
        "and saved a screenshot and report. Top themes today were open-source "
        "tooling and developer productivity. Raw headlines and logs are in the report."
    )


def main() -> None:
    result = run_job(
        "research the top Hacker News stories and summarize them",
        browser_research_agent,
        profile="researcher",
        memory=AgentMemory("agent_state"),
        skills=SkillRegistry("skills"),
        recorder=TraceRecorder("traces"),
        evaluate=True,
    )
    print(result.summary)
    print(f"\nJob ID    : {result.job_id}")
    print(f"Skill     : {result.skill.name if result.skill else '(none)'}")
    print(f"Trace     : {result.trace_path}")
    print(f"Report    : {result.report_path}")
    if result.proposal:
        print("\nImprovement proposal (needs approval):")
        print(" ", result.proposal.memory_suggestion)


if __name__ == "__main__":
    main()
