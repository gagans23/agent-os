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


def test_search_sessions_finds_by_command_and_answer(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.save_session("job-aaa", {
        "job_id": "job-aaa", "command": "ask how do I add fractions",
        "final": "Add the numerators when denominators match.",
        "created_at": "2026-06-01T10:00:00+00:00",
    })
    mem.save_session("job-bbb", {
        "job_id": "job-bbb", "command": "run summarize the quarterly budget",
        "final": "Revenue rose; costs held flat.",
        "created_at": "2026-06-02T10:00:00+00:00",
    })
    # match on the question text
    hits = mem.search_sessions("fractions")
    assert hits and hits[0]["job_id"] == "job-aaa"
    # match on the answer text (the 'final' field is indexed too)
    hits2 = mem.search_sessions("budget revenue")
    assert any(h["job_id"] == "job-bbb" for h in hits2)
    mem.close()


def test_search_sessions_handles_punctuation_and_empty(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    mem.save_session("job-1", {"job_id": "job-1", "command": "ask about taxes?",
                               "final": "See your accountant."})
    assert mem.search_sessions("") == []
    # punctuation in the query must not raise an FTS syntax error
    assert isinstance(mem.search_sessions('taxes? "quoted"'), list)
    mem.close()


def test_reindex_sessions_backfills_existing_files(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    # Write a session file directly (as if from before the index existed).
    (tmp_path / "state" / "sessions" / "old.json").write_text(
        '{"job_id": "old", "command": "run the photosynthesis demo", '
        '"final": "Plants convert light to energy."}')
    n = mem.reindex_sessions()
    assert n >= 1
    hits = mem.search_sessions("photosynthesis")
    assert any(h["job_id"] == "old" for h in hits)
    mem.close()
