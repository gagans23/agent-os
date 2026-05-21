"""
agent_memory — persistent memory for the agent platform.

Layout:

    agent_state/
      MEMORY.md          human-readable running notes (facts, workflows)
      USER.md            user preferences / profile
      state.db           structured store (facts, prefs, outcomes)
      sessions/          one JSON file per job session

Stores: preferences, recurring contacts, project facts, previous failed fixes,
successful workflows, common command patterns, and per-job outcomes (used by the
self-improvement loop). Standard-library only (sqlite3 + markdown files).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MEMORY_SEED = "# Agent Memory\n\nRunning notes the agent has learned. Append-only-ish.\n"
_USER_SEED = "# User Profile\n\nPreferences and recurring context for this user.\n"


class AgentMemory:
    """Markdown + SQLite persistent memory store."""

    def __init__(self, root: str | Path = "agent_state") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sessions").mkdir(exist_ok=True)
        self.memory_md = self.root / "MEMORY.md"
        self.user_md = self.root / "USER.md"
        if not self.memory_md.exists():
            self.memory_md.write_text(_MEMORY_SEED)
        if not self.user_md.exists():
            self.user_md.write_text(_USER_SEED)
        self.db_path = self.root / "state.db"
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                key TEXT PRIMARY KEY, value TEXT, category TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS prefs (
                key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                job_id TEXT PRIMARY KEY, task TEXT, profile TEXT, skill TEXT,
                score REAL, certification TEXT, created_at TEXT
            );
            """
        )
        self._db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    # --- structured facts --------------------------------------------------

    def remember(self, key: str, value: str, category: str = "fact") -> None:
        self._db.execute(
            "INSERT INTO facts(key,value,category,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "category=excluded.category, updated_at=excluded.updated_at",
            (key, value, category, self._now()),
        )
        self._db.commit()

    def recall(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM facts WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        rows = self._db.execute(
            "SELECT key,value,category FROM facts WHERE lower(key) LIKE ? "
            "OR lower(value) LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- preferences -------------------------------------------------------

    def set_pref(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO prefs(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, self._now()),
        )
        self._db.commit()

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute("SELECT value FROM prefs WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # --- running notes -----------------------------------------------------

    def note(self, text: str) -> None:
        with self.memory_md.open("a") as f:
            f.write(f"\n- {self._now()}: {text}")

    # --- outcomes (for self-improvement) -----------------------------------

    def record_outcome(self, job_id: str, task: str, score: float, certification: str,
                       profile: str = "", skill: str = "") -> None:
        self._db.execute(
            "INSERT INTO outcomes(job_id,task,profile,skill,score,certification,created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET "
            "score=excluded.score, certification=excluded.certification",
            (job_id, task, profile, skill, score, certification, self._now()),
        )
        self._db.commit()

    def recent_outcomes(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM outcomes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- sessions ----------------------------------------------------------

    def save_session(self, job_id: str, payload: dict[str, Any]) -> Path:
        path = self.root / "sessions" / f"{job_id}.json"
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    def context_for(self, command: str, max_facts: int = 5) -> str:
        """Build a small memory context string to hand an agent."""
        facts = self.search(command, limit=max_facts)
        lines = [f"{f['key']}: {f['value']}" for f in facts]
        prefs = self.user_md.read_text().strip()
        ctx = "## Relevant memory\n" + ("\n".join(lines) if lines else "(none yet)")
        return ctx + "\n\n## User\n" + prefs

    def close(self) -> None:
        self._db.close()
