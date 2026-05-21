"""
skill_registry — load reusable procedures ("skills") from SKILL.md files.

Each skill lives in skills/<name>/SKILL.md with YAML frontmatter + a markdown
body:

    ---
    name: bisad-email-digest
    description: Summarize only new BISAD inbox items.
    triggers: [bisad, email, digest, inbox, unread]
    expected_artifacts: [final.md, ninja_report.json]
    ---
    ## Procedure
    1. ...
    ## Pitfalls
    - ...
    ## Verification
    - ...

The registry loads all skills and matches an incoming command to the best one by
trigger-keyword overlap. Skills are documentation the agent (and reviewer) reads;
they are not executed automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    procedure: str = ""
    pitfalls: str = ""
    verification: str = ""
    path: Path | None = None

    def trigger_score(self, command: str) -> int:
        cmd = command.lower()
        return sum(1 for t in self.triggers if t.lower() in cmd)


_SECTION_RE = re.compile(r"^##+\s*(.+?)\s*$", re.MULTILINE)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            return meta, parts[2]
    return {}, text


def _section(body: str, name: str) -> str:
    """Extract a markdown ## section by (case-insensitive) heading name."""
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == name.lower():
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            return body[start:end].strip()
    return ""


def parse_skill_file(path: str | Path) -> Skill:
    path = Path(path)
    text = path.read_text()
    meta, body = _split_frontmatter(text)
    return Skill(
        name=str(meta.get("name", path.parent.name)),
        description=str(meta.get("description", "")),
        triggers=[str(t) for t in (meta.get("triggers") or [])],
        expected_artifacts=[str(a) for a in (meta.get("expected_artifacts") or [])],
        procedure=_section(body, "Procedure"),
        pitfalls=_section(body, "Pitfalls"),
        verification=_section(body, "Verification"),
        path=path,
    )


class SkillRegistry:
    """Loads and matches skills from a skills/ directory."""

    def __init__(self, root: str | Path = "skills") -> None:
        self.root = Path(root)
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        if not self.root.exists():
            return
        for skill_md in sorted(self.root.glob("*/SKILL.md")):
            skill = parse_skill_file(skill_md)
            self._skills[skill.name] = skill

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def match(self, command: str) -> Skill | None:
        """Return the skill whose triggers best match the command, or None."""
        best: Skill | None = None
        best_score = 0
        for skill in self._skills.values():
            score = skill.trigger_score(command)
            if score > best_score:
                best, best_score = skill, score
        return best
