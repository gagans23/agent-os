"""Tests for health checks, sender allowlist, and token health."""

from __future__ import annotations

from agent_os.allowlist import Allowlist, normalize_sender
from agent_os.health import run_health_checks
from agent_os.token_health import check_tokens

# --- health ----------------------------------------------------------------

def test_health_report_ok(tmp_path) -> None:
    report = run_health_checks(
        state_dir=tmp_path / "state", skills_dir="skills", traces_dir=tmp_path / "traces"
    )
    assert report.status in {"ok", "degraded"}
    assert any(c.name == "ninja_harness" and c.ok for c in report.checks)
    assert any(c.name == "jobs_db" and c.ok for c in report.checks)
    assert "Health:" in report.render()


def test_health_dict(tmp_path) -> None:
    report = run_health_checks(state_dir=tmp_path / "s", skills_dir="skills", traces_dir=tmp_path / "t")
    d = report.to_dict()
    assert "status" in d and "checks" in d


# --- allowlist --------------------------------------------------------------

def test_normalize_phone_and_username() -> None:
    assert normalize_sender("+1 (555) 123-4567") == "+15551234567"
    assert normalize_sender("0044 7700 900000") == "+447700900000"
    assert normalize_sender("Alice") == "alice"


def test_allowlist_fail_closed_when_empty() -> None:
    al = Allowlist()
    assert al.is_allowed("+15551234567") is False  # empty allowlist denies all


def test_allowlist_allows_normalized_match() -> None:
    al = Allowlist(["+1 555 123 4567"])
    assert al.is_allowed("+15551234567") is True
    assert al.is_allowed("+1 (555) 123-4567") is True
    assert al.is_allowed("+19999999999") is False


def test_allowlist_load_from_file(tmp_path) -> None:
    p = tmp_path / "allow.txt"
    p.write_text("# owners\n+15551234567\nalice\n")
    al = Allowlist(path=p)
    assert len(al) == 2
    assert al.is_allowed("Alice") is True


# --- token health -----------------------------------------------------------

def test_token_missing(monkeypatch) -> None:
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    [status] = check_tokens(["WHATSAPP_TOKEN"])
    assert status.present is False
    assert status.healthy is False
    assert "missing" in status.detail


def test_token_present_shape_ok(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "x" * 40)
    [status] = check_tokens(["WHATSAPP_TOKEN"])
    assert status.present and status.shape_ok and status.healthy
    assert status.valid is None  # not live-validated


def test_token_too_short(monkeypatch) -> None:
    monkeypatch.setenv("T", "short")
    [status] = check_tokens(["T"], min_len=16)
    assert status.shape_ok is False and status.healthy is False


def test_token_validator_hook_and_no_leak(monkeypatch) -> None:
    secret = "supersecretvalue-1234567890"
    monkeypatch.setenv("WHATSAPP_TOKEN", secret)
    seen = {}

    def validator(name, value):
        seen["value"] = value
        return True, "validated"

    [status] = check_tokens(["WHATSAPP_TOKEN"], validator=validator)
    assert status.valid is True
    # The status object must never carry the secret value.
    assert secret not in str(status.to_dict())
