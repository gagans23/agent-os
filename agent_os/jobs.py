"""
jobs — SQLite persistent job store.

Every run is a durable job record with a lifecycle (running → done/failed) and
its evaluation outcome, so the platform survives restarts and you can look a job
up later by id (or short prefix) from a WhatsApp/CLI command.

    agent_state/jobs.db   (git-ignored)

Standard library only (sqlite3).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JobStore:
    """Durable store of job records."""

    def __init__(self, db_path: str | Path = "agent_state/jobs.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                command TEXT,
                profile TEXT,
                skill TEXT,
                status TEXT,              -- running | done | failed
                ninja_score REAL,
                certification TEXT,       -- PASS | WARN | FAIL
                verdict TEXT,             -- platform verdict (incl. profile threshold)
                flagged INTEGER,
                trace_path TEXT,
                report_path TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self._db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    # --- lifecycle ---------------------------------------------------------

    def create(self, job_id: str, command: str, profile: str = "", skill: str = "") -> None:
        now = self._now()
        self._db.execute(
            "INSERT OR REPLACE INTO jobs(job_id,command,profile,skill,status,flagged,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (job_id, command, profile, skill, "running", 0, now, now),
        )
        self._db.commit()

    def finish(self, job_id: str, *, status: str = "done", ninja_score: float | None = None,
               certification: str | None = None, verdict: str | None = None,
               flagged: bool | None = None, trace_path: str | None = None,
               report_path: str | None = None, error: str | None = None) -> None:
        self._db.execute(
            "UPDATE jobs SET status=?, ninja_score=?, certification=?, verdict=?, "
            "flagged=?, trace_path=?, report_path=?, error=?, updated_at=? WHERE job_id=?",
            (status, ninja_score, certification, verdict,
             int(bool(flagged)) if flagged is not None else 0,
             trace_path, report_path, error, self._now(), job_id),
        )
        self._db.commit()

    # --- queries -----------------------------------------------------------

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self._db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def find(self, token: str) -> dict[str, Any] | None:
        """Resolve a job by exact id, then suffix, then substring (short ids)."""
        if (exact := self.get(token)) is not None:
            return exact
        like_suffix = f"%{token}"
        row = self._db.execute(
            "SELECT * FROM jobs WHERE job_id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (like_suffix,),
        ).fetchone()
        if row:
            return dict(row)
        row = self._db.execute(
            "SELECT * FROM jobs WHERE job_id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"%{token}%",),
        ).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        total = self._db.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        by_cert: dict[str, int] = {}
        for row in self._db.execute(
            "SELECT certification, COUNT(*) c FROM jobs WHERE certification IS NOT NULL "
            "GROUP BY certification"
        ).fetchall():
            by_cert[row["certification"]] = row["c"]
        evaluated = sum(by_cert.values())
        pass_rate = (by_cert.get("PASS", 0) / evaluated) if evaluated else 0.0
        return {"total": total, "by_certification": by_cert, "pass_rate": round(pass_rate, 4)}

    def close(self) -> None:
        self._db.close()
