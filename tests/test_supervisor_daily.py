"""Tests for the process supervisor and daily eval summary."""

from __future__ import annotations

import sys
import threading
import time

from agent_os.daily_eval import daily_summary
from agent_os.jobs import JobStore
from agent_os.supervisor import Supervisor, SupervisorPolicy


def test_supervisor_gives_up_after_max_restarts() -> None:
    # A command that always fails fast; never reaches healthy_uptime.
    cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
    sup = Supervisor(
        cmd,
        SupervisorPolicy(max_restarts=2, backoff_base=0, backoff_max=0, healthy_uptime=999),
        sleep=lambda d: None,
    )
    sup.run(install_signals=False)
    assert sup.gave_up is True
    # 1 initial start + 2 restarts before giving up.
    assert sup.starts == 3
    assert sup.last_exit_code == 1


def test_supervisor_stop_terminates_child() -> None:
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    sup = Supervisor(cmd, SupervisorPolicy(max_restarts=0), sleep=lambda d: None)
    t = threading.Thread(target=sup.run, kwargs={"install_signals": False}, daemon=True)
    t.start()
    time.sleep(0.5)        # let the child start
    sup.stop()
    t.join(timeout=5)
    assert not t.is_alive()


def test_daily_summary_job_fallback(tmp_path) -> None:
    store = JobStore(tmp_path / "state" / "jobs.db")
    store.create("j1", "task one")
    store.finish("j1", status="done", certification="PASS", verdict="PASS", ninja_score=92)
    store.create("j2", "task two")
    store.finish("j2", status="done", certification="WARN", verdict="WARN",
                 ninja_score=70, flagged=True)
    store.close()

    summary = daily_summary(state_dir=tmp_path / "state")
    assert "Daily agent-os eval" in summary
    assert "pass rate" in summary
    assert "flagged" in summary
