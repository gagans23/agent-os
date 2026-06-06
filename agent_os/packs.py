"""
packs — curated role packs: bundles of skills (+ recommended connectors) that
get a non-technical user or a pro coder productive in one step.

A *role pack* is a directory of ready-to-use `SKILL.md` procedures plus a
`pack.yaml` manifest and an `mcp.example.json` recommending (never auto-wiring)
the MCP servers those skills pair well with. Bundled packs live under
``agent_os/packs/`` and ship with the wheel; extra roots can be added via
``AGENT_OS_PACKS_PATH``.

True to core:

* **Pluggable, never faked.** Skills are plain Markdown procedures (model-agnostic,
  run through whatever provider you configured). The MCP recommendation is an
  *example* with **no credentials** — installing it is your separate, explicit
  step (see `docs/mcp.md`).
* **Default-deny, but human-initiated installs are fine.** The *agent* never
  installs a pack on its own (that's the gated learning loop's job). `pack-install`
  is something **you** type — an explicit human action, audited like any command.
* **Local-first, dependency-light.** stdlib + PyYAML (already a dep). No network.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def packs_roots(env: str = "AGENT_OS_PACKS_PATH") -> list[Path]:
    """The bundled packs dir plus any extra roots from ``AGENT_OS_PACKS_PATH``
    (os.pathsep-separated)."""
    roots = [Path(__file__).parent / "packs"]
    extra = os.environ.get(env, "")
    roots.extend(Path(p) for p in extra.split(os.pathsep) if p.strip())
    return roots


@dataclass
class Pack:
    """One curated role pack."""

    name: str
    description: str
    path: Path
    recommended_mcp: list[str] = field(default_factory=list)
    recommended_model: str | None = None
    skills: list[str] = field(default_factory=list)  # skill directory names

    def skills_dir(self) -> Path:
        return self.path / "skills"

    def mcp_example(self) -> dict | None:
        """The pack's recommended MCP servers (credential-free template), if any."""
        import json

        p = self.path / "mcp.example.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (ValueError, OSError):
            return None


def _discover_skill_dirs(pack_dir: Path) -> list[str]:
    """Skill directory names (those containing a SKILL.md) inside a pack."""
    skills_dir = pack_dir / "skills"
    if not skills_dir.exists():
        return []
    return sorted(d.name for d in skills_dir.iterdir()
                  if d.is_dir() and (d / "SKILL.md").exists())


def _load_pack(pack_dir: Path) -> Pack | None:
    manifest = pack_dir / "pack.yaml"
    if not manifest.exists():
        return None
    try:
        meta = yaml.safe_load(manifest.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None
    name = str(meta.get("name", pack_dir.name))
    return Pack(
        name=name,
        description=str(meta.get("description", "")),
        path=pack_dir,
        recommended_mcp=[str(s) for s in (meta.get("recommended_mcp") or [])],
        recommended_model=meta.get("recommended_model"),
        skills=_discover_skill_dirs(pack_dir),
    )


def list_packs(roots: list[Path] | None = None) -> list[Pack]:
    """All discoverable role packs (first root wins on name collision)."""
    roots = roots or packs_roots()
    packs: dict[str, Pack] = {}
    for root in roots:
        if not root.exists():
            continue
        for pack_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            pack = _load_pack(pack_dir)
            if pack and pack.name not in packs:
                packs[pack.name] = pack
    return list(packs.values())


def get_pack(name: str, roots: list[Path] | None = None) -> Pack | None:
    for pack in list_packs(roots):
        if pack.name == name:
            return pack
    return None


@dataclass
class InstallReport:
    """What an install did (or would do, in a dry run)."""

    pack: str
    installed: list[str] = field(default_factory=list)   # skill names copied
    skipped: list[str] = field(default_factory=list)     # already present
    dest: str = ""
    dry_run: bool = False


def install_pack(pack: Pack, skills_dest: str | Path, *, dry_run: bool = False) -> InstallReport:
    """Copy a pack's skills into the destination skills directory. Existing skills
    of the same name are left untouched (your local edits win), and reported as
    skipped. Never writes credentials and never touches MCP config."""
    dest = Path(skills_dest)
    report = InstallReport(pack=pack.name, dest=str(dest), dry_run=dry_run)
    for skill_name in pack.skills:
        target = dest / skill_name
        if target.exists():
            report.skipped.append(skill_name)
            continue
        if not dry_run:
            shutil.copytree(pack.skills_dir() / skill_name, target)
        report.installed.append(skill_name)
    return report
