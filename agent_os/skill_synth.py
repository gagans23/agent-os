"""
skill_synth — the closed learning loop: turn a successful, novel task into a
reusable skill **proposal**.

Inspired by self-improving agents (e.g. Nous Research's Hermes Agent, which
"creates skills from experience"), but kept true to agent-os's core: a learned
skill is **never written silently**. After a job that (a) scored well, (b) matched
no existing skill, and (c) was non-trivial, this builds a `SKILL.md` *draft* from
the job's own trace. The router enqueues it for human approval (default-deny);
only `/approve` writes it into `skills/`. The agent proposes; the human installs.

Pure functions here (no I/O beyond what's passed in) so the logic is easy to test;
persistence + the approval gate live in the command router.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_os.skill_registry import _derive_triggers

_WORD = re.compile(r"[a-z0-9]+")
_SLUG_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "my",
    "me", "please", "run", "ask", "do", "get", "make", "create", "this", "that",
    "from", "into", "about", "how", "what", "your", "you",
}


@dataclass
class SkillDraft:
    """A proposed SKILL.md, pending human approval."""

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    procedure: str = ""
    verification: str = ""
    source_job_id: str = ""

    def to_markdown(self) -> str:
        trig = ", ".join(self.triggers)
        md = (
            "---\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"triggers: [{trig}]\n"
            "---\n\n"
            f"<!-- Proposed by agent-os from job {self.source_job_id}. "
            "Review and edit before relying on it. -->\n\n"
            "## Procedure\n"
            f"{self.procedure}\n"
        )
        if self.verification:
            md += f"\n## Verification\n{self.verification}\n"
        return md


def slugify(command: str, *, max_words: int = 5) -> str:
    """A short, file-system-safe skill name derived from the task."""
    toks = [t for t in _WORD.findall(command.lower()) if t not in _SLUG_STOP]
    return "-".join(toks[:max_words]) or "task"


def _procedure_from_trace(trace: dict[str, Any]) -> str:
    """Reconstruct a numbered procedure from the trace's steps + tool calls."""
    lines: list[str] = []
    for s in trace.get("steps", []) or []:
        out = (s.get("output") or "").strip()
        if out:
            lines.append(out)
    for t in trace.get("tool_calls", []) or []:
        name = t.get("tool_name") or "tool"
        lines.append(f"Use the `{name}` tool.")
    if not lines:
        return "1. (Capture the concrete steps that made this work.)"
    return "\n".join(f"{i}. {ln}" for i, ln in enumerate(lines, 1))


def trace_complexity(trace: dict[str, Any]) -> int:
    """How much the agent actually did — steps plus tool calls."""
    return len(trace.get("steps", []) or []) + len(trace.get("tool_calls", []) or [])


def propose_skill(
    command: str,
    *,
    score: float,
    certification: str,
    matched_skill: Any,
    trace: dict[str, Any],
    existing_names: set[str],
    min_score: float = 80.0,
    min_complexity: int = 3,
) -> SkillDraft | None:
    """Return a SkillDraft iff this run is worth turning into a reusable skill:
    it succeeded (PASS or score >= min_score), no existing skill already covered
    it, and it was non-trivial. Otherwise None (the common case — no spam)."""
    if matched_skill is not None:
        return None
    if certification != "PASS" and float(score) < min_score:
        return None
    if trace_complexity(trace) < min_complexity:
        return None
    name = slugify(command)
    if name in existing_names:
        return None
    triggers = _derive_triggers(command, "")[:8]
    if not triggers:
        return None
    desc = command.strip()
    if len(desc) > 100:
        desc = desc[:97] + "…"
    return SkillDraft(
        name=name,
        description=desc,
        triggers=triggers,
        procedure=_procedure_from_trace(trace),
        verification="Re-run the task and confirm the result matches the expected outcome.",
        source_job_id=str(trace.get("job_id") or ""),
    )
