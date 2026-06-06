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
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_os.jobs import _ensure_wal

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
        self._db = sqlite3.connect(self.db_path, timeout=10.0)
        self._db.row_factory = sqlite3.Row
        # busy_timeout before touching journal mode: concurrent opens (the swarm)
        # wait for any brief lock rather than erroring with "database is locked".
        self._db.execute("PRAGMA busy_timeout=10000")
        _ensure_wal(self._db)
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
        # Full-text index over past sessions for cross-session recall (/recall).
        # FTS5 is part of standard SQLite builds; if this build lacks it we set a
        # flag and fall back to a substring scan over the session JSON files, so
        # recall always works — just less ranked.
        try:
            self._db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5("
                "job_id UNINDEXED, ts UNINDEXED, command, body)"
            )
            self._db.commit()
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False

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
        self.index_session(job_id, payload)
        return path

    # --- cross-session recall (FTS5) ---------------------------------------

    @staticmethod
    def _session_body(payload: dict[str, Any]) -> str:
        """Searchable text for one session: the task plus its answer and tags."""
        parts = [
            str(payload.get("command") or ""),
            str(payload.get("final") or payload.get("answer") or ""),
            str(payload.get("skill") or ""),
            str(payload.get("certification") or ""),
        ]
        return "\n".join(p for p in parts if p)

    def index_session(self, job_id: str, payload: dict[str, Any]) -> None:
        """Add/refresh one session in the recall index. Idempotent per job_id."""
        if not self._fts:
            return
        command = str(payload.get("command") or "")
        ts = str(payload.get("created_at") or payload.get("ts") or self._now())
        body = self._session_body(payload)
        self._db.execute("DELETE FROM sessions_fts WHERE job_id=?", (job_id,))
        self._db.execute(
            "INSERT INTO sessions_fts(job_id, ts, command, body) VALUES(?,?,?,?)",
            (job_id, ts, command, body),
        )
        self._db.commit()

    def reindex_sessions(self) -> int:
        """Rebuild the recall index from the session JSON files on disk (so recall
        covers sessions written before the index existed). Returns the count."""
        if not self._fts:
            return 0
        self._db.execute("DELETE FROM sessions_fts")
        n = 0
        for p in (self.root / "sessions").glob("*.json"):
            try:
                payload = json.loads(p.read_text())
            except (ValueError, OSError):
                continue
            command = str(payload.get("command") or "")
            ts = str(payload.get("created_at") or datetime.fromtimestamp(
                p.stat().st_mtime, tz=UTC).isoformat())
            self._db.execute(
                "INSERT INTO sessions_fts(job_id, ts, command, body) VALUES(?,?,?,?)",
                (p.stem, ts, command, self._session_body(payload)),
            )
            n += 1
        self._db.commit()
        return n

    @staticmethod
    def _fts_match(query: str) -> str:
        """Turn free text into a lenient FTS5 MATCH: prefix-match each word, OR'd
        (recall favors breadth; bm25 ranks). Strips FTS operators to avoid syntax
        errors on punctuation in user input."""
        terms = re.findall(r"\w+", query.lower())
        return " OR ".join(f"{t}*" for t in terms)

    def search_sessions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search past sessions. Uses FTS5 (ranked + snippets) when available,
        else a substring scan over the session JSON files."""
        query = (query or "").strip()
        if not query:
            return []
        if self._fts:
            # Lazily backfill the index the first time recall runs on old data.
            count = self._db.execute("SELECT count(*) FROM sessions_fts").fetchone()[0]
            if count == 0 and any((self.root / "sessions").glob("*.json")):
                self.reindex_sessions()
            match = self._fts_match(query)
            if match:
                rows = self._db.execute(
                    "SELECT job_id, ts, command, "
                    "snippet(sessions_fts, 3, '«', '»', '…', 12) AS snippet "
                    "FROM sessions_fts WHERE sessions_fts MATCH ? "
                    "ORDER BY bm25(sessions_fts) LIMIT ?",
                    (match, limit),
                ).fetchall()
                if rows:
                    return [dict(r) for r in rows]
        return self._search_sessions_fallback(query, limit)

    def _search_sessions_fallback(self, query: str, limit: int) -> list[dict[str, Any]]:
        ql = query.lower()
        out: list[dict[str, Any]] = []
        for payload in self.recent_sessions(limit=200):
            body = self._session_body(payload)
            if ql in body.lower() or any(t in body.lower() for t in re.findall(r"\w+", ql)):
                snippet = body.replace("\n", " ")[:120]
                out.append({
                    "job_id": str(payload.get("job_id") or ""),
                    "ts": str(payload.get("created_at") or ""),
                    "command": str(payload.get("command") or ""),
                    "snippet": snippet,
                })
            if len(out) >= limit:
                break
        return out

    def recent_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Most-recent session payloads (newest first), for cost/metering rollups."""
        files = sorted((self.root / "sessions").glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        out: list[dict[str, Any]] = []
        for p in files[:limit]:
            try:
                out.append(json.loads(p.read_text()))
            except (ValueError, OSError):
                continue
        return out

    def context_for(self, command: str, max_facts: int = 5) -> str:
        """Build a small memory context string to hand an agent."""
        facts = self.search(command, limit=max_facts)
        lines = [f"{f['key']}: {f['value']}" for f in facts]
        prefs = self.user_md.read_text().strip()
        ctx = "## Relevant memory\n" + ("\n".join(lines) if lines else "(none yet)")
        return ctx + "\n\n## User\n" + prefs

    def close(self) -> None:
        self._db.close()
