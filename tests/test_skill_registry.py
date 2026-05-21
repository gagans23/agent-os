"""Tests for skill_registry (uses the repo's skills/ dir)."""

from __future__ import annotations

from pathlib import Path

from agent_os.skill_registry import SkillRegistry, parse_skill_file

SKILLS = Path("skills")


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
