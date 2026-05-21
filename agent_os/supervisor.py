"""
supervisor — keep a long-running bridge/agent process alive.

Runs a command, waits for it, and restarts it on exit with exponential backoff.
Restarts are capped (so a hard-failing process doesn't loop forever); if the
process stays up past `healthy_uptime`, the restart counter resets. Handles
SIGTERM/SIGINT to shut the child down cleanly. Emits structured logs.

    Supervisor(["python", "bridge.py"]).run()

Standard library only.
"""

from __future__ import annotations

import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass

from agent_os.logging_setup import get_logger

_log = get_logger("supervisor")


@dataclass
class SupervisorPolicy:
    max_restarts: int = 10          # consecutive restarts before giving up
    backoff_base: float = 1.0
    backoff_max: float = 30.0
    healthy_uptime: float = 30.0    # uptime (s) that resets the restart counter
    term_grace: float = 10.0        # seconds to wait after SIGTERM before SIGKILL


class Supervisor:
    """Supervises a single child process with restart-on-failure."""

    def __init__(self, command: list[str], policy: SupervisorPolicy | None = None,
                 *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not command:
            raise ValueError("Supervisor requires a non-empty command.")
        self.command = command
        self.policy = policy or SupervisorPolicy()
        self._sleep = sleep
        self._clock = clock
        self._stop = False
        self._proc: subprocess.Popen | None = None
        # observability
        self.starts = 0
        self.gave_up = False
        self.last_exit_code: int | None = None

    def _spawn(self) -> subprocess.Popen:
        self.starts += 1
        _log.info("start", extra={"command": self.command[:3], "attempt": self.starts})
        return subprocess.Popen(self.command)

    def stop(self) -> None:
        """Request shutdown and terminate the child if running."""
        self._stop = True
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=self.policy.term_grace)
            except subprocess.TimeoutExpired:
                _log.warning("kill_after_grace", extra={"pid": proc.pid})
                proc.kill()

    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):  # noqa: ANN001
            _log.info("signal", extra={"signal": signum})
            self.stop()
        try:
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)
        except ValueError:
            # Not on the main thread (e.g. under tests) — skip signal handlers.
            pass

    def run(self, install_signals: bool = True) -> None:
        """Blocking supervise loop. Returns when stopped or restarts exhausted."""
        if install_signals:
            self._install_signal_handlers()
        restarts = 0
        while not self._stop:
            started = self._clock()
            self._proc = self._spawn()
            self.last_exit_code = self._proc.wait()
            uptime = self._clock() - started
            if self._stop:
                break
            if uptime >= self.policy.healthy_uptime:
                restarts = 0  # it ran long enough; treat as a fresh failure
            restarts += 1
            if restarts > self.policy.max_restarts:
                self.gave_up = True
                _log.error("gave_up", extra={"restarts": restarts - 1,
                                              "last_exit_code": self.last_exit_code})
                break
            delay = min(self.policy.backoff_max, self.policy.backoff_base * (2 ** (restarts - 1)))
            _log.warning("restart", extra={"restart": restarts, "delay": round(delay, 2),
                                           "exit_code": self.last_exit_code})
            self._sleep(delay)
