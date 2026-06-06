"""Tests for curated role packs (discovery + install)."""

from __future__ import annotations

from agent_os.packs import get_pack, install_pack, list_packs
from agent_os.skill_registry import SkillRegistry


def test_bundled_packs_are_discoverable() -> None:
    names = {p.name for p in list_packs()}
    assert {"productivity", "dev"} <= names


def test_pack_has_skills_and_recommendations() -> None:
    dev = get_pack("dev")
    assert dev is not None
    assert "code-review" in dev.skills and "write-unit-tests" in dev.skills
    assert "filesystem" in dev.recommended_mcp
    # mcp.example.json is a credential-free template (no real secrets baked in)
    example = dev.mcp_example()
    assert example and "servers" in example and "filesystem" in example["servers"]
    assert "ghp_" not in str(example)  # no real token value bundled


def test_install_pack_copies_skills_and_is_matchable(tmp_path) -> None:
    dest = tmp_path / "skills"
    dest.mkdir()
    pack = get_pack("productivity")
    report = install_pack(pack, dest)
    assert set(report.installed) == set(pack.skills)
    assert not report.skipped
    # The copied skills are real and loadable by the registry.
    reg = SkillRegistry(dest)
    assert reg.get("inbox-triage") is not None
    assert (dest / "meeting-notes" / "SKILL.md").exists()


def test_install_pack_skips_existing(tmp_path) -> None:
    dest = tmp_path / "skills"
    dest.mkdir()
    pack = get_pack("productivity")
    install_pack(pack, dest)
    again = install_pack(pack, dest)
    assert set(again.skipped) == set(pack.skills)  # nothing re-copied
    assert not again.installed


def test_install_dry_run_writes_nothing(tmp_path) -> None:
    dest = tmp_path / "skills"
    dest.mkdir()
    pack = get_pack("dev")
    report = install_pack(pack, dest, dry_run=True)
    assert report.installed and report.dry_run
    assert list(dest.iterdir()) == []  # dry run touched nothing


def test_unknown_pack_is_none() -> None:
    assert get_pack("does-not-exist") is None
