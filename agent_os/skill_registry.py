"""
skill_registry — load reusable procedures ("skills") from SKILL.md files.

Two formats are supported, auto-detected:

1. **agent-os format** — explicit `triggers` for deterministic matching, plus
   `## Procedure` / `## Pitfalls` / `## Verification` sections:

       ---
       name: bisad-email-digest
       description: Summarize only new BISAD inbox items.
       triggers: [bisad, email, digest, inbox, unread]
       expected_artifacts: [final.md, ninja_report.json]
       ---
       ## Procedure
       1. ...

2. **Agent Skills standard** (https://agentskills.io — used by anthropics/skills
   and the knowledge-work plugins) — only `name` + `description` are required, the
   whole markdown body is the instruction set, and `allowed-tools` is optional:

       ---
       name: pdf
       description: Extract text and tables from PDF files, fill forms, ...
       license: Apache-2.0
       allowed-tools: [Read, Bash]
       ---
       # PDF skill
       Step-by-step instructions...

For the second format we **derive trigger keywords from the name + description**
so the deterministic matcher still works, and treat the whole body as the
procedure. This lets you drop in any open Agent Skills tree
(`git clone` + `AGENT_OS_SKILLS_PATH`) and have agent-os match and inject it —
through whatever model you've configured (Ollama, OpenAI, …), never hardwired to
one vendor.

Skills are documentation the agent (and reviewer) reads; the runner injects the
matched skill into the agent's context. They are not executed automatically.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "you",
    "your", "but", "can", "has", "have", "how", "what", "when", "why", "out",
    "use", "uses", "using", "used", "into", "onto", "over", "any", "all", "etc",
    "such", "via", "per", "its", "their", "them", "they", "then", "than", "who",
    "whom", "whose", "which", "while", "where", "skill", "skills", "claude",
    "agent", "agents", "task", "tasks", "user", "users", "help", "helps",
    "create", "creating", "creates", "make", "makes", "based", "specific",
}


def _derive_triggers(name: str, description: str, limit: int = 12) -> list[str]:
    """Keyword triggers from the name + description (for Agent-Skills-format skills
    that don't declare explicit triggers)."""
    text = f"{name.replace('-', ' ').replace('_', ' ')} {description}".lower()
    seen: list[str] = []
    for tok in _WORD.findall(text):
        if tok not in _STOP and tok not in seen:
            seen.append(tok)
        if len(seen) >= limit:
            break
    return seen


@dataclass
class Skill:
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    procedure: str = ""
    pitfalls: str = ""
    verification: str = ""
    allowed_tools: list[str] = field(default_factory=list)
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
    text = path.read_text(errors="ignore")
    meta, body = _split_frontmatter(text)
    name = str(meta.get("name", path.parent.name))
    description = str(meta.get("description", ""))

    triggers = [str(t) for t in (meta.get("triggers") or [])]
    if not triggers:  # Agent Skills format: derive from name + description.
        triggers = _derive_triggers(name, description)

    # agent-os format has explicit sections; Agent Skills format does not — there,
    # the whole body is the instruction set.
    procedure = _section(body, "Procedure")
    if not procedure:
        procedure = body.strip()

    # `allowed-tools` (Agent Skills) or `allowed_tools`.
    allowed = meta.get("allowed-tools", meta.get("allowed_tools")) or []
    if isinstance(allowed, str):
        allowed = [allowed]

    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        expected_artifacts=[str(a) for a in (meta.get("expected_artifacts") or [])],
        procedure=procedure,
        pitfalls=_section(body, "Pitfalls"),
        verification=_section(body, "Verification"),
        allowed_tools=[str(t) for t in allowed],
        path=path,
    )


def skill_roots_from_env(primary: str | Path = "skills",
                         env: str = "AGENT_OS_SKILLS_PATH") -> list[Path]:
    """The primary skills dir plus any extra roots from `AGENT_OS_SKILLS_PATH`
    (os.pathsep-separated). Lets you import an open Agent Skills tree::

        git clone https://github.com/anthropics/skills
        export AGENT_OS_SKILLS_PATH=$PWD/skills/skills
    """
    roots = [Path(primary)]
    extra = os.environ.get(env, "")
    roots.extend(Path(p) for p in extra.split(os.pathsep) if p.strip())
    return roots


class SkillRegistry:
    """Loads and matches skills from one or more skills/ directories.

    Discovery is recursive (`**/SKILL.md`), so nested trees — Agent Skills
    categories or knowledge-work-plugin `skills/` folders — are picked up. When the
    same skill name appears in multiple roots, the earlier root wins (your local
    skills take precedence over imported ones)."""

    def __init__(self, root: str | Path | list[str | Path] = "skills") -> None:
        roots = root if isinstance(root, list) else [root]
        self.roots = [Path(r) for r in roots]
        self.root = self.roots[0] if self.roots else Path("skills")
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        seen: set[Path] = set()
        for root in self.roots:
            if not root.exists():
                continue
            for skill_md in sorted(root.rglob("SKILL.md")):
                resolved = skill_md.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                skill = parse_skill_file(skill_md)
                self._skills.setdefault(skill.name, skill)  # first root wins

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
