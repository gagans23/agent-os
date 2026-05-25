"""Tests for skill_registry (uses the repo's skills/ dir)."""

from __future__ import annotations

from pathlib import Path

from agent_os.skill_registry import (
    SkillRegistry,
    parse_skill_file,
    skill_roots_from_env,
)

SKILLS = Path("skills")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_loads_repo_skills() -> None:
    reg = SkillRegistry(SKILLS)
    names = {s.name for s in reg.all()}
    assert {"bisad-email-digest", "browser-research", "meta-token-refresh"} <= names


def test_parse_sections(tmp_path) -> None:
    p = tmp_path / "s" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "---\nname: demo\ndescription: d\ntriggers: [alpha, beta]\n"
        "expected_artifacts: [final.md]\n---\n"
        "## Procedure\nstep one\n## Pitfalls\nbe careful\n## Verification\ncheck it\n"
    )
    skill = parse_skill_file(p)
    assert skill.name == "demo"
    assert skill.triggers == ["alpha", "beta"]
    assert "step one" in skill.procedure
    assert "be careful" in skill.pitfalls
    assert "check it" in skill.verification


def test_match_by_trigger() -> None:
    reg = SkillRegistry(SKILLS)
    assert reg.match("summarize the BISAD unread inbox").name == "bisad-email-digest"
    assert reg.match("open the browser and research this").name == "browser-research"
    assert reg.match("got a 401 unauthorized token error").name == "meta-token-refresh"


def test_match_none_when_no_trigger() -> None:
    reg = SkillRegistry(SKILLS)
    assert reg.match("xyzzy nothing matches here") is None


# --- Module 4: Agent Skills standard compatibility -------------------------

AGENT_SKILL = (
    "---\n"
    "name: pdf\n"
    "description: Extract text and tables from PDF files and fill PDF forms.\n"
    "license: Apache-2.0\n"
    "allowed-tools: [Read, Bash]\n"
    "---\n"
    "# PDF skill\n\n"
    "Use pdfplumber to extract text. Then fill form fields as requested.\n"
)


def test_parses_agent_skills_format_without_triggers(tmp_path) -> None:
    skill = parse_skill_file(_write(tmp_path / "pdf" / "SKILL.md", AGENT_SKILL))
    assert skill.name == "pdf"
    # Triggers are derived from name + description (no explicit `triggers:`).
    assert "pdf" in skill.triggers and "extract" in skill.triggers
    # The whole body becomes the instruction set.
    assert "pdfplumber" in skill.procedure
    assert skill.allowed_tools == ["Read", "Bash"]


def test_derived_triggers_make_imported_skill_matchable(tmp_path) -> None:
    _write(tmp_path / "pdf" / "SKILL.md", AGENT_SKILL)
    reg = SkillRegistry(tmp_path)
    assert reg.match("extract the form fields from invoice.pdf").name == "pdf"


def test_recursive_discovery_of_nested_skill_trees(tmp_path) -> None:
    # anthropics/skills layout: skills/<category>/<skill>/SKILL.md
    _write(tmp_path / "document" / "pdf" / "SKILL.md", AGENT_SKILL)
    _write(tmp_path / "creative" / "music" / "SKILL.md",
           "---\nname: music\ndescription: Compose short melodies.\n---\n# Music\nHum it.\n")
    reg = SkillRegistry(tmp_path)
    assert {"pdf", "music"} <= {s.name for s in reg.all()}


def test_multiple_roots_local_wins_on_collision(tmp_path) -> None:
    local = _write(tmp_path / "local" / "pdf" / "SKILL.md",
                   "---\nname: pdf\ndescription: LOCAL pdf skill.\n---\n# local\n")
    _write(tmp_path / "imported" / "pdf" / "SKILL.md", AGENT_SKILL)
    reg = SkillRegistry([tmp_path / "local", tmp_path / "imported"])
    assert reg.get("pdf").description == "LOCAL pdf skill."
    assert reg.get("pdf").path == local


def test_skill_roots_from_env(tmp_path, monkeypatch) -> None:
    import os

    monkeypatch.delenv("AGENT_OS_SKILLS_PATH", raising=False)
    assert skill_roots_from_env("skills") == [Path("skills")]
    monkeypatch.setenv("AGENT_OS_SKILLS_PATH", f"{tmp_path}/a{os.pathsep}{tmp_path}/b")
    roots = skill_roots_from_env("skills")
    assert roots[0] == Path("skills") and Path(f"{tmp_path}/a") in roots
