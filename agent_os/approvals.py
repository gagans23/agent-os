"""
approvals — a durable queue for actions awaiting human approval.

When the risk classifier flags a task (write/send/deploy), the platform does NOT
run it. Instead it enqueues an approval here and replies with an id. The human
runs /approve <id> (execute) or /reject <id> (cancel). Nothing privileged happens
without that explicit decision.

    agent_state/approvals.db   (git-ignored)
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ApprovalStore:
    """SQLite-backed approval queue."""

    def __init__(self, db_path: str | Path = "agent_state/approvals.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                command TEXT,
                profile TEXT,
                risk_level TEXT,
                reason TEXT,
                status TEXT,          -- pending | approved | rejected
                job_id TEXT,
                created_at TEXT,
                decided_at TEXT
            )
            """
        )
        self._db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def enqueue(self, command: str, profile: str, risk_level: str, reason: str) -> str:
        approval_id = uuid.uuid4().hex[:8]
        self._db.execute(
            "INSERT INTO approvals(id,command,profile,risk_level,reason,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (approval_id, command, profile, risk_level, reason, "pending", self._now()),
        )
        self._db.commit()
        return approval_id

    def get(self, token: str) -> dict[str, Any] | None:
        row = self._db.execute("SELECT * FROM approvals WHERE id=?", (token,)).fetchone()
        if row:
            return dict(row)
        row = self._db.execute(
            "SELECT * FROM approvals WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"{token}%",),
        ).fetchone()
        return dict(row) if row else None

    def list(self, status: str | None = "pending", limit: int = 20) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def set_decision(self, approval_id: str, status: str, job_id: str | None = None) -> None:
        self._db.execute(
            "UPDATE approvals SET status=?, job_id=?, decided_at=? WHERE id=?",
            (status, job_id, self._now(), approval_id),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
