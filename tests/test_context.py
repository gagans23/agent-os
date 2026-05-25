"""Tests for the knowledge base / context store ("the brain")."""

from __future__ import annotations

from agent_os.context import ContextStore, chunk_text

NOTES = """Adding fractions

To add fractions with the same denominator, add the numerators and keep the denominator.
For example 1/4 + 2/4 = 3/4.

Multiplying fractions

To multiply fractions, multiply the numerators and multiply the denominators.
For example 2/3 * 3/4 = 6/12 = 1/2.

Photosynthesis

Plants convert sunlight into energy. This is unrelated to maths.
"""


def test_chunk_text_splits_on_paragraphs() -> None:
    chunks = chunk_text(NOTES, chunk_size=120)
    assert len(chunks) >= 3
    assert all(len(c) <= 240 for c in chunks)  # hard cap-ish


def test_ingest_and_stats(tmp_path) -> None:
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_text(NOTES, source="maths-notes")
    s = store.stats()
    assert s["docs"] == 1 and s["chunks"] >= 3
    store.close()


def test_ingest_file(tmp_path) -> None:
    p = tmp_path / "notes.md"
    p.write_text(NOTES)
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_file(p)
    assert store.stats()["chunks"] >= 3
    store.close()


def test_search_retrieves_relevant_chunk(tmp_path) -> None:
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_text(NOTES, source="maths-notes")
    hits = store.search("how do I add fractions?", k=3)
    assert hits
    top = hits[0].text.lower()
    assert "add" in top and "numerator" in top
    # The unrelated photosynthesis chunk should not be the top hit.
    assert "photosynthesis" not in top
    store.close()


def test_build_context_tags_sources(tmp_path) -> None:
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_text(NOTES, source="maths-notes")
    ctx = store.build_context("multiplying fractions", max_chars=500)
    assert "[source: maths-notes]" in ctx
    assert "multiply" in ctx.lower()
    store.close()


def test_references_for_grounding(tmp_path) -> None:
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_text(NOTES, source="maths-notes")
    refs = store.references("add fractions", k=2)
    assert refs and any("numerator" in r.lower() for r in refs)
    store.close()


def test_empty_store_returns_nothing(tmp_path) -> None:
    store = ContextStore(tmp_path / "ctx.db")
    assert store.search("anything") == []
    assert store.build_context("anything") == ""
    store.close()


# --- semantic / hybrid retrieval (with a pluggable embedder) ----------------

def test_embeddings_stored_at_ingest_and_hybrid_search(tmp_path) -> None:
    from agent_os.providers import EchoProvider

    store = ContextStore(tmp_path / "ctx.db", embedder=EchoProvider().embed)
    store.ingest_text(NOTES, source="maths-notes")
    s = store.stats()
    assert s["embeddings"] == s["chunks"] and s["embeddings"] >= 3
    # Hybrid search still surfaces the relevant chunk.
    hits = store.search("how do I add fractions?", k=3)
    assert hits and "numerator" in hits[0].text.lower()
    store.close()


def test_reindex_embeddings_backfills(tmp_path) -> None:
    from agent_os.providers import EchoProvider

    # Ingest in keyword-only mode (no embedder), then wire one in and backfill.
    store = ContextStore(tmp_path / "ctx.db")
    store.ingest_text(NOTES, source="maths-notes")
    assert store.stats()["embeddings"] == 0
    store.embedder = EchoProvider().embed
    n = store.reindex_embeddings()
    assert n >= 3 and store.stats()["embeddings"] == n
    store.close()
