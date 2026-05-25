"""Tests for the tamper-evident audit log."""

from __future__ import annotations

import sqlite3

from agent_os.audit import AuditLog


def test_record_and_recent(tmp_path) -> None:
    log = AuditLog(tmp_path / "audit.db")
    log.record("/run delete things", actor="alice", risk="WRITE", decision="queued")
    log.record("/approve abc", actor="alice", decision="executed", job_id="job-1")
    recent = log.recent()
    assert len(recent) == 2
    assert recent[0]["command"] == "/approve abc"
    assert log.count() == 2
    log.close()


def test_chain_verifies_intact(tmp_path) -> None:
    log = AuditLog(tmp_path / "audit.db")
    for i in range(5):
        log.record(f"/cmd {i}", decision="ok")
    ok, broken = log.verify()
    assert ok is True and broken is None
    log.close()


def test_tampering_breaks_chain(tmp_path) -> None:
    db = tmp_path / "audit.db"
    log = AuditLog(db)
    for i in range(4):
        log.record(f"/cmd {i}", decision="ok")
    log.close()

    # Tamper directly with the DB (simulate an attacker editing a past entry).
    con = sqlite3.connect(db)
    con.execute("UPDATE audit SET command='/cmd HACKED' WHERE seq=2")
    con.commit()
    con.close()

    log2 = AuditLog(db)
    ok, broken = log2.verify()
    assert ok is False
    assert broken == 2
    log2.close()


def test_genesis_links_first_entry(tmp_path) -> None:
    log = AuditLog(tmp_path / "audit.db")
    entry = log.record("/first", decision="ok")
    rows = log.recent()
    assert rows[0]["prev_hash"] == "GENESIS"
    assert rows[0]["entry_hash"] == entry["entry_hash"]
    log.close()
