"""Tests for retry/timeout reliability utilities."""

from __future__ import annotations

import sys

import pytest

from agent_os.reliability import RetryPolicy, retry, run_subprocess, with_retries


def test_with_retries_succeeds_after_failures() -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    out = with_retries(flaky, RetryPolicy(attempts=5, base_delay=0), sleep=lambda d: None)
    assert out == "ok"
    assert calls["n"] == 3


def test_with_retries_reraises_after_exhaustion() -> None:
    def always():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        with_retries(always, RetryPolicy(attempts=2, base_delay=0), sleep=lambda d: None)


def test_retry_only_on_listed_exceptions() -> None:
    def boom():
        raise KeyError("not retried")

    # KeyError not in retry_on → raised immediately, no retries
    with pytest.raises(KeyError):
        with_retries(boom, RetryPolicy(attempts=3, base_delay=0, retry_on=(ValueError,)),
                     sleep=lambda d: None)


def test_retry_decorator() -> None:
    state = {"n": 0}

    @retry(RetryPolicy(attempts=3, base_delay=0))
    def f():
        state["n"] += 1
        if state["n"] < 2:
            raise ValueError()
        return 42

    assert f() == 42


def test_run_subprocess_ok() -> None:
    res = run_subprocess([sys.executable, "-c", "print('hi')"])
    assert res.ok
    assert "hi" in res.stdout


def test_run_subprocess_timeout() -> None:
    res = run_subprocess([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)
    assert res.timed_out
    assert not res.ok
    assert res.exit_code == 124
