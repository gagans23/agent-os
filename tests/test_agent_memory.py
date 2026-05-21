"""Tests for agent_memory."""

from __future__ import annotations

from agent_os.agent_memory import AgentMemory


def test_seeds_files(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    assert (tmp_path / "state" / "MEMORY.md").exists()
    assert (tmp_path / "state" / "USER.md").exists()
    assert (tmp_path / "state" / "state.db").exists()
    mem.close()


def test_remember_recall_search(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.remember("contact:teacher", "Ms. Lee <lee@bisad.example>", category="contact")
    assert mem.recall("contact:teacher").startswith("Ms. Lee")
    hits = mem.search("teacher")
    assert any("teacher" in h["key"] for h in hits)
    mem.close()


def test_prefs(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.set_pref("report_style", "concise")
    assert mem.get_pref("report_style") == "concise"
    assert mem.get_pref("missing", "default") == "default"
    mem.close()


def test_outcomes_and_sessions(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.record_outcome("job-1", "task a", 91.4, "PASS", profile="researcher", skill="browser-research")
    mem.record_outcome("job-2", "task b", 70.0, "WARN", profile="qa")
    recent = mem.recent_outcomes()
    assert len(recent) == 2
    path = mem.save_session("job-1", {"x": 1})
    assert path.exists()
    mem.close()


def test_context_for(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.remember("project:ninja", "trace-first eval harness")
    ctx = mem.context_for("ninja eval")
    assert "Relevant memory" in ctx and "User" in ctx
    mem.close()
