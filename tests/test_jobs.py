"""Tests for the SQLite persistent job store."""

from __future__ import annotations

from agent_os.jobs import JobStore


def test_create_and_get(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create("job-1", "do a thing", profile="researcher", skill="browser-research")
    job = store.get("job-1")
    assert job["command"] == "do a thing"
    assert job["status"] == "running"
    assert job["profile"] == "researcher"
    store.close()


def test_finish_updates_record(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create("job-2", "task")
    store.finish("job-2", status="done", ninja_score=91.4, certification="PASS",
                 verdict="PASS", flagged=False, trace_path="t.json", report_path="r.json")
    job = store.get("job-2")
    assert job["status"] == "done"
    assert job["ninja_score"] == 91.4
    assert job["certification"] == "PASS"
    assert job["trace_path"] == "t.json"
    store.close()


def test_find_by_prefix_suffix_substring(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create("job-20260521-1200-f6df6f", "x")
    assert store.find("job-20260521-1200-f6df6f")["job_id"].endswith("f6df6f")
    assert store.find("f6df6f") is not None      # suffix
    assert store.find("0521") is not None         # substring
    assert store.find("zzzz") is None
    store.close()


def test_list_and_status_filter(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create("a", "one")
    store.create("b", "two")
    store.finish("b", status="done", certification="PASS", verdict="PASS")
    assert len(store.list()) == 2
    assert len(store.list(status="done")) == 1
    store.close()


def test_stats(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    for i, cert in enumerate(["PASS", "PASS", "WARN", "FAIL"]):
        store.create(f"j{i}", "t")
        store.finish(f"j{i}", status="done", certification=cert, verdict=cert, ninja_score=80)
    stats = store.stats()
    assert stats["total"] == 4
    assert stats["by_certification"]["PASS"] == 2
    assert stats["pass_rate"] == 0.5
    store.close()


def test_failed_job_records_error(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create("j", "t")
    store.finish("j", status="failed", error="boom")
    assert store.get("j")["status"] == "failed"
    assert store.get("j")["error"] == "boom"
    store.close()
