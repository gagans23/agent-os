"""Tests for the risk classifier and approval queue."""

from __future__ import annotations

from agent_os.approvals import ApprovalStore
from agent_os.risk import RiskLevel, classify_risk

# --- risk classifier --------------------------------------------------------

def test_read_only_auto() -> None:
    for task in ["summarize the inbox", "list recent jobs", "research transformers",
                 "check status", "show the report"]:
        a = classify_risk(task)
        assert a.level == RiskLevel.READ_ONLY
        assert a.requires_approval is False


def test_send_requires_approval() -> None:
    a = classify_risk("send a WhatsApp message to the team")
    assert a.level == RiskLevel.SEND
    assert a.requires_approval is True


def test_write_requires_approval() -> None:
    a = classify_risk("delete the old records")
    assert a.level == RiskLevel.WRITE
    assert a.requires_approval is True


def test_deploy_is_highest() -> None:
    # Mentions both write and deploy → highest (DEPLOY) wins.
    a = classify_risk("update the code and deploy to production")
    assert a.level == RiskLevel.DEPLOY
    assert a.requires_approval is True


def test_assessment_dict() -> None:
    d = classify_risk("publish the release").to_dict()
    assert d["level"] == "DEPLOY" and d["requires_approval"] is True


# --- approval queue ---------------------------------------------------------

def test_enqueue_and_get(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.db")
    aid = store.enqueue("send msg", "operator", "SEND", "SEND: matched send")
    rec = store.get(aid)
    assert rec["status"] == "pending"
    assert rec["risk_level"] == "SEND"
    assert store.get(aid[:4])["id"] == aid   # prefix match
    store.close()


def test_list_pending_and_decision(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.db")
    a1 = store.enqueue("delete x", "operator", "WRITE", "r")
    store.enqueue("deploy y", "operator", "DEPLOY", "r")
    assert len(store.list(status="pending")) == 2
    store.set_decision(a1, "approved", job_id="job-1")
    assert store.get(a1)["status"] == "approved"
    assert store.get(a1)["job_id"] == "job-1"
    assert len(store.list(status="pending")) == 1
    store.close()
