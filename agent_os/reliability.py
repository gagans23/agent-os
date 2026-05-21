"""
reliability — retry and timeout policies.

- RetryPolicy + retry()/with_retries(): bounded retries with exponential backoff
  and jitter, for transient failures (network, sandbox flake).
- run_subprocess(): run a command with an enforced timeout, returning a
  structured result (never hangs the platform).

Standard library only. No external services are called here.
"""

from __future__ import annotations

import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from agent_os.logging_setup import get_logger

_log = get_logger("reliability")
T = TypeVar("T")


@dataclass
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 10.0
    jitter: float = 0.1
    retry_on: tuple[type[BaseException], ...] = (Exception,)

    def delay_for(self, attempt: int) -> float:
        raw = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return raw + random.uniform(0, self.jitter)


def with_retries(fn: Callable[[], T], policy: RetryPolicy | None = None,
                 *, sleep: Callable[[float], None] = time.sleep) -> T:
    """Call fn() with bounded retries. Re-raises the last error if all fail."""
    policy = policy or RetryPolicy()
    last: BaseException | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            return fn()
        except policy.retry_on as exc:  # type: ignore[misc]
            last = exc
            if attempt >= policy.attempts:
                break
            delay = policy.delay_for(attempt)
            _log.warning("retry", extra={"attempt": attempt, "delay": round(delay, 3),
                                         "error": f"{type(exc).__name__}: {exc}"})
            sleep(delay)
    assert last is not None
    raise last


def retry(policy: RetryPolicy | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator form of with_retries."""
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return with_retries(lambda: fn(*args, **kwargs), policy)
        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapper
    return deco


@dataclass
class SubprocessResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


# Default per-action timeouts (seconds). Override per call as needed.
DEFAULT_TIMEOUTS: dict[str, float] = {
    "agent": 300.0,
    "tool": 60.0,
    "healthcheck": 15.0,
    "eval": 120.0,
}


def run_subprocess(command: list[str], *, stdin: str | None = None,
                   timeout: float = 300.0, env: dict[str, str] | None = None) -> SubprocessResult:
    """Run a command with an enforced timeout. Never hangs the caller."""
    try:
        proc = subprocess.run(
            command, input=stdin, capture_output=True, text=True,
            timeout=timeout, env=env, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _log.warning("subprocess_timeout", extra={"command": command[:3], "timeout": timeout})
        return SubprocessResult(
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            exit_code=124, timed_out=True,
        )
    return SubprocessResult(stdout=proc.stdout or "", stderr=proc.stderr or "",
                            exit_code=proc.returncode)
