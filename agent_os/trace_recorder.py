"""
trace_recorder — record everything a job does into a reproducible bundle.

Every job gets its own directory:

    traces/<job_id>/
      command.txt          the original command / task
      stdout.log           appended log lines
      screenshots/         any saved screenshots
      final.md             the final answer
      trace.json           the Ninja Harness-compatible trace (Custom JSON)
      ninja_report.json    the evaluation result (written by the runner)

Without traces, the agent cannot improve intelligently. This module is
dependency-light (standard library only) and produces a trace dict that the
Ninja Harness Custom JSON adapter parses directly.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JobRecorder:
    """Records a single job's trajectory and artifacts."""

    def __init__(self, job_dir: Path, job_id: str, agent_name: str, task: str) -> None:
        self.dir = job_dir
        self.job_id = job_id
        self.agent_name = agent_name
        self.task = task
        self.started_at = datetime.now(UTC)
        self._steps: list[dict[str, Any]] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._final_output = ""
        self._metadata: dict[str, Any] = {"job_id": job_id}
        (self.dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (self.dir / "command.txt").write_text(task)
        self._log_path = self.dir / "stdout.log"
        self._log_path.touch()

    # --- logging & steps ---------------------------------------------------

    def log(self, line: str) -> None:
        with self._log_path.open("a") as f:
            f.write(line.rstrip("\n") + "\n")

    def add_step(self, step_type: str, output: str = "", *, status: str = "completed",
                 error: str | None = None, agent_name: str | None = None) -> None:
        self._steps.append({
            "agent_name": agent_name or self.agent_name,
            "step_type": step_type,
            "output": output,
            "status": status,
            "error": error,
        })
        self.log(f"[{step_type}] {output}")

    def add_tool_call(self, tool_name: str, arguments: dict | None = None,
                      result: str | None = None, *, status: str = "success",
                      error: str | None = None) -> None:
        self._tool_calls.append({
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result": result,
            "status": status,
            "error": error,
        })
        self.log(f"[tool] {tool_name}({arguments or {}}) -> {status}")

    def add_screenshot(self, name: str, src_path: str | Path | None = None,
                       data: bytes | None = None) -> Path:
        dest = self.dir / "screenshots" / name
        if data is not None:
            dest.write_bytes(data)
        elif src_path is not None:
            shutil.copyfile(src_path, dest)
        self._metadata.setdefault("screenshots", []).append(name)
        return dest

    def set_final(self, text: str) -> None:
        self._final_output = text
        (self.dir / "final.md").write_text(text)

    def set_metadata(self, **kwargs: Any) -> None:
        self._metadata.update(kwargs)

    # --- trace export ------------------------------------------------------

    def to_trace(self) -> dict[str, Any]:
        """Return a Ninja Harness Custom JSON-compatible trace dict."""
        return {
            "run_id": self.job_id,
            "agent_name": self.agent_name,
            "task": self.task,
            "final_output": self._final_output,
            "steps": self._steps,
            "tool_calls": self._tool_calls,
            "handoffs": [],
            "guardrail_events": [],
            "metadata": self._metadata,
        }

    def save_trace(self) -> Path:
        path = self.dir / "trace.json"
        path.write_text(json.dumps(self.to_trace(), indent=2))
        return path

    def save_report(self, report: Any) -> Path:
        """Persist the Ninja Harness evaluation (a pydantic model or dict)."""
        path = self.dir / "ninja_report.json"
        if hasattr(report, "model_dump_json"):
            path.write_text(report.model_dump_json(indent=2))
        else:
            path.write_text(json.dumps(report, indent=2, default=str))
        return path


class TraceRecorder:
    """Factory for per-job recorders rooted at a traces/ directory."""

    def __init__(self, root: str | Path = "traces") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def start(self, command: str, agent_name: str = "agent", task: str | None = None,
              job_id: str | None = None) -> JobRecorder:
        job_id = job_id or f"job-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return JobRecorder(job_dir, job_id, agent_name, task or command)
