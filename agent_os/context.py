"""
context — the "brain": ingest your notes/files into a personal knowledge base
that agents retrieve from.

This is the local-first answer to Onyx-style RAG: dependency-light (SQLite +
keyword/BM25-lite retrieval, standard library only) so a non-technical user can
run it with zero infrastructure. Semantic retrieval is a **pluggable embedder**
you supply (Ollama/OpenAI/etc.) — never bundled, never a hidden network call.

Example (Ahaan's maths brain):
    ctx = ContextStore()
    ctx.ingest_text(open("ahaan_maths_notes.md").read(), source="maths-notes")
    print(ctx.build_context("how do I add fractions?"))   # → grounded context

The retrieved context is designed to feed an agent AND to be handed to Ninja
Harness as grounding references, so answers can be scored against the source.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# embedder: list of texts -> list of vectors. You supply it (e.g. via providers).
Embedder = Callable[[list[str]], list[list[float]]]

_WORD = re.compile(r"[a-z0-9]{2,}")
_STOP = {"the", "and", "for", "that", "this", "with", "from", "are", "was", "you",
         "your", "but", "can", "has", "have", "how", "what", "when", "why", "out"}


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def chunk_text(text: str, chunk_size: int = 800) -> list[str]:
    """One chunk per paragraph (the natural retrieval unit), hard-splitting any
    paragraph longer than chunk_size. Paragraph granularity keeps unrelated
    topics in separate chunks so retrieval stays precise."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    for para in paras:
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            while para:
                chunks.append(para[:chunk_size])
                para = para[chunk_size:]
    return chunks


@dataclass
class Chunk:
    chunk_id: int
    doc_id: int
    source: str
    text: str
    score: float = 0.0


class ContextStore:
    """SQLite-backed personal knowledge base with keyword (and optional semantic) search."""

    def __init__(self, db_path: str | Path = "agent_state/context.db",
                 embedder: Embedder | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS docs (
                doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, title TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER, ordinal INTEGER, text TEXT, source TEXT
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id INTEGER PRIMARY KEY, vec TEXT
            );
            """
        )
        self._db.commit()
        self.embedder = embedder

    # --- ingestion ---------------------------------------------------------

    def ingest_text(self, text: str, source: str = "text", title: str = "",
                    chunk_size: int = 800) -> int:
        now = datetime.now(UTC).isoformat()
        cur = self._db.execute(
            "INSERT INTO docs(source,title,created_at) VALUES(?,?,?)",
            (source, title or source, now),
        )
        doc_id = cur.lastrowid
        new: list[tuple[int, str]] = []
        for i, ch in enumerate(chunk_text(text, chunk_size)):
            c = self._db.execute(
                "INSERT INTO chunks(doc_id,ordinal,text,source) VALUES(?,?,?,?)",
                (doc_id, i, ch, source),
            )
            new.append((c.lastrowid, ch))
        self._db.commit()
        self._embed_chunks(new)
        return doc_id

    def _embed_chunks(self, chunks: list[tuple[int, str]]) -> None:
        """Compute and persist embeddings for new chunks (only if an embedder is
        configured). Failures degrade gracefully to keyword-only search."""
        if not self.embedder or not chunks:
            return
        try:
            vecs = self.embedder([c[1] for c in chunks])
        except Exception:  # noqa: BLE001 - never let a model hiccup block ingestion
            return
        for (cid, _text), vec in zip(chunks, vecs):
            self._db.execute("INSERT OR REPLACE INTO embeddings(chunk_id,vec) VALUES(?,?)",
                             (cid, json.dumps([float(x) for x in vec])))
        self._db.commit()

    def ingest_file(self, path: str | Path, chunk_size: int = 800) -> int:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No such file: {p}")
        return self.ingest_text(p.read_text(errors="ignore"), source=p.name,
                                title=p.stem, chunk_size=chunk_size)

    # --- retrieval ---------------------------------------------------------

    def _all_chunks(self) -> list[sqlite3.Row]:
        return self._db.execute("SELECT chunk_id,doc_id,source,text FROM chunks").fetchall()

    def _bm25(self, rows: list[sqlite3.Row], q_terms: list[str]) -> dict[int, float]:
        """BM25-lite keyword score per chunk_id (no model needed)."""
        n = len(rows)
        df: Counter[str] = Counter()
        toks_per_chunk = []
        for r in rows:
            toks = _tokens(r["text"])
            toks_per_chunk.append(toks)
            for t in set(toks):
                df[t] += 1
        avg_len = sum(len(t) for t in toks_per_chunk) / n or 1.0
        k1, b = 1.5, 0.75
        out: dict[int, float] = {}
        for r, toks in zip(rows, toks_per_chunk):
            tf = Counter(toks)
            dl = len(toks) or 1
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                num = tf[term] * (k1 + 1)
                den = tf[term] + k1 * (1 - b + b * dl / avg_len)
                score += idf * num / den
            if score > 0:
                out[r["chunk_id"]] = score
        return out

    def _semantic(self, query: str) -> dict[int, float]:
        """Cosine similarity per chunk_id against the query embedding.

        Returns {} when no embedder is configured, none are stored, or the model
        call fails — so search always degrades cleanly to keyword-only."""
        if not self.embedder:
            return {}
        stored = self._db.execute("SELECT chunk_id, vec FROM embeddings").fetchall()
        if not stored:
            return {}
        try:
            qvec = self.embedder([query])[0]
        except Exception:  # noqa: BLE001 - degrade to keyword-only
            return {}
        qn = math.sqrt(sum(x * x for x in qvec)) or 1.0
        out: dict[int, float] = {}
        for row in stored:
            vec = json.loads(row["vec"])
            if len(vec) != len(qvec):
                continue
            dot = sum(a * b for a, b in zip(qvec, vec))
            vn = math.sqrt(sum(x * x for x in vec)) or 1.0
            out[row["chunk_id"]] = dot / (qn * vn)
        return out

    def search(self, query: str, k: int = 5, alpha: float = 0.5) -> list[Chunk]:
        """Retrieve the top-k chunks.

        Keyword-only (BM25-lite) by default. When a `embedder` is configured and
        embeddings exist, blends keyword and semantic scores (both min-max
        normalized) as ``alpha*semantic + (1-alpha)*keyword`` — a hybrid that
        catches paraphrases keyword search misses while keeping exact hits."""
        rows = self._all_chunks()
        if not rows:
            return []
        q_terms = _tokens(query)
        bm = self._bm25(rows, q_terms) if q_terms else {}
        sem = self._semantic(query)
        if not bm and not sem:
            return []

        def _norm(d: dict[int, float]) -> dict[int, float]:
            if not d:
                return {}
            lo, hi = min(d.values()), max(d.values())
            rng = (hi - lo) or 1.0
            return {cid: (v - lo) / rng for cid, v in d.items()}

        bmn, semn = _norm(bm), _norm(sem)
        # Blend only when both signals exist; otherwise use whichever we have.
        if bmn and semn:
            combined = {cid: alpha * semn.get(cid, 0.0) + (1 - alpha) * bmn.get(cid, 0.0)
                        for cid in set(bmn) | set(semn)}
        else:
            combined = semn or bmn
        by_id = {r["chunk_id"]: r for r in rows}
        scored = [Chunk(r["chunk_id"], r["doc_id"], r["source"], r["text"], round(combined[cid], 4))
                  for cid, r in ((c, by_id[c]) for c in combined)]
        scored.sort(key=lambda c: -c.score)
        return scored[:k]

    def build_context(self, query: str, k: int = 5, max_chars: int = 2000) -> str:
        """Return a grounded context string (top chunks, each tagged with its source)."""
        hits = self.search(query, k)
        out, used = [], 0
        for c in hits:
            block = f"[source: {c.source}] {c.text.strip()}"
            if used + len(block) > max_chars:
                break
            out.append(block)
            used += len(block)
        return "\n\n".join(out)

    def references(self, query: str, k: int = 5) -> list[str]:
        """Top chunks as a list of references for Ninja Harness grounding."""
        return [c.text.strip() for c in self.search(query, k)]

    def reindex_embeddings(self) -> int:
        """Embed any chunks that don't yet have an embedding (e.g. after wiring a
        provider to a store that was populated in keyword-only mode). Returns the
        number of chunks embedded. No-op without an embedder."""
        if not self.embedder:
            return 0
        rows = self._db.execute(
            "SELECT c.chunk_id, c.text FROM chunks c "
            "LEFT JOIN embeddings e ON e.chunk_id=c.chunk_id WHERE e.chunk_id IS NULL"
        ).fetchall()
        pending = [(r["chunk_id"], r["text"]) for r in rows]
        self._embed_chunks(pending)
        return len(pending)

    def stats(self) -> dict[str, int]:
        d = self._db.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        c = self._db.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        e = self._db.execute("SELECT COUNT(*) c FROM embeddings").fetchone()["c"]
        return {"docs": d, "chunks": c, "embeddings": e}

    def close(self) -> None:
        self._db.close()
