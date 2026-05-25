"""
audit — a tamper-evident, append-only record of every command and decision.

Each entry is hash-chained: its hash covers the entry's content **and the
previous entry's hash**, so any insertion, deletion, or edit anywhere in the log
breaks the chain and is detectable via `verify()`. This gives an enterprise-grade
audit trail for a system that takes real-world actions — who asked for what, how
it was classified, whether it was approved, and what happened.

    agent_state/audit.db   (git-ignored)
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_GENESIS = "GENESIS"


class AuditLog:
    """Append-only, hash-chained audit log."""

    def __init__(self, db_path: str | Path = "agent_state/audit.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, actor TEXT, command TEXT, risk TEXT,
                decision TEXT, job_id TEXT, detail TEXT,
                prev_hash TEXT, entry_hash TEXT
            )
            """
        )
        self._db.commit()

    @staticmethod
    def _hash(parts: list[str]) -> str:
        return hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()

    def _last_hash(self) -> str:
        row = self._db.execute(
            "SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row["entry_hash"] if row else _GENESIS

    def record(self, command: str, *, actor: str = "local", risk: str = "",
               decision: str = "", job_id: str = "", detail: str = "") -> dict[str, Any]:
        ts = datetime.now(UTC).isoformat()
        prev = self._last_hash()
        entry_hash = self._hash([ts, actor, command, risk, decision, job_id, detail, prev])
        self._db.execute(
            "INSERT INTO audit(ts,actor,command,risk,decision,job_id,detail,prev_hash,entry_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (ts, actor, command, risk, decision, job_id, detail, prev, entry_hash),
        )
        self._db.commit()
        return {"ts": ts, "actor": actor, "command": command, "risk": risk,
                "decision": decision, "job_id": job_id, "entry_hash": entry_hash}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain. Returns (ok, first_broken_seq)."""
        prev = _GENESIS
        for row in self._db.execute("SELECT * FROM audit ORDER BY seq ASC"):
            expected = self._hash([row["ts"], row["actor"], row["command"], row["risk"],
                                   row["decision"], row["job_id"], row["detail"], prev])
            if row["prev_hash"] != prev or row["entry_hash"] != expected:
                return False, row["seq"]
            prev = row["entry_hash"]
        return True, None

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"]

    def close(self) -> None:
        self._db.close()
