"""Tests for trace_recorder."""

from __future__ import annotations

import json

from agent_os.trace_recorder import TraceRecorder


def test_records_job_bundle(tmp_path) -> None:
    rec = TraceRecorder(tmp_path / "traces")
    job = rec.start("do the thing", agent_name="researcher")
    job.add_step("plan", "plan it")
    job.add_tool_call("web_search", {"q": "x"}, result="found", status="success")
    job.add_screenshot("shot.txt", data=b"img")
    job.set_final("All done.")
    trace_path = job.save_trace()

    assert (job.dir / "command.txt").read_text() == "do the thing"
    assert (job.dir / "final.md").read_text() == "All done."
    assert (job.dir / "stdout.log").exists()
    assert (job.dir / "screenshots" / "shot.txt").read_bytes() == b"img"

    trace = json.loads(trace_path.read_text())
    assert trace["agent_name"] == "researcher"
    assert trace["final_output"] == "All done."
    assert len(trace["steps"]) == 1
    assert trace["tool_calls"][0]["tool_name"] == "web_search"


def test_trace_is_ninja_parseable(tmp_path) -> None:
    from ninja_harness.adapters import detect_adapter

    rec = TraceRecorder(tmp_path / "traces")
    job = rec.start("task", agent_name="a")
    job.set_final("answer")
    run = detect_adapter(job.to_trace()).parse(job.to_trace())
    assert run.agent_name == "a"
    assert run.final_output == "answer"


def test_save_report_pydantic(tmp_path) -> None:
    from ninja_harness.schemas import EvaluationResult

    rec = TraceRecorder(tmp_path / "traces")
    job = rec.start("task")
    job.set_final("x")
    result = EvaluationResult(run_id="r", ninja_score=90, grade="A", certification="PASS")
    p = job.save_report(result)
    assert "ninja_score" in p.read_text()
