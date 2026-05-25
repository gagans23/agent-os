# The Brain 🧠 — your own context

> Module 1. `agent_os/context.py`. The local-first answer to Onyx-style RAG: a
> personal knowledge base your agents retrieve from, grounded and scored.

The keystone of the personal-OS vision is an agent that is **self-aware of *your*
context** — your notes, your files, your decisions — not a generic model guessing
from training data. The Brain is where that context lives.

```python
from agent_os.context import ContextStore
ctx = ContextStore()                       # SQLite, zero infrastructure
ctx.ingest_file("ahaan_maths_notes.md")
print(ctx.build_context("how do I add fractions?"))   # → grounded, source-tagged
```

## Design principles

- **Local-first, dependency-light.** SQLite + the standard library only. No vector
  DB, no Redis, no MinIO, no Docker. A non-technical user — or a child — can run it.
- **Pluggable, never faked.** Keyword retrieval (BM25-lite) works with **no model
  at all**. Semantic retrieval is a **pluggable embedder you supply** (via
  [providers](providers.md)). agent-os never bundles a model or makes a hidden
  network call.
- **Everything is grounded and scored.** Retrieved chunks are handed to
  [Ninja Harness](https://github.com/gagans23/ninja-harness) as grounding
  references, so every answer is *scored against its sources* — ungrounded
  answers get flagged.

## How it works

### 1. Ingestion → chunks

`ingest_text()` / `ingest_file()` split a document into **one chunk per
paragraph** (`chunk_text`, blank-line delimited), hard-splitting any paragraph
longer than `chunk_size` (default 800 chars). Paragraph granularity keeps
unrelated topics in separate chunks, so retrieval stays precise (Ahaan's
"adding fractions" never bleeds into an unrelated "photosynthesis" note).

Each chunk is stored in `chunks`; the parent document in `docs`.

### 2. Retrieval → keyword, semantic, or hybrid

`search(query, k=5, alpha=0.5)` returns the top-`k` chunks.

- **Keyword (always available):** a compact **BM25-lite** scorer
  (`k1=1.5, b=0.75`, with idf over the corpus and length normalization). No model
  needed. Tokenization lowercases, keeps `[a-z0-9]{2,}`, and drops a small stoplist.
- **Semantic (when an embedder is configured):** at ingest time each chunk is
  embedded and the vector stored in `embeddings`. At query time the query is
  embedded once and scored by **cosine similarity** against the stored vectors.
- **Hybrid:** when both signals exist, scores are **min-max normalized** and
  blended as `alpha * semantic + (1 - alpha) * keyword`. This catches paraphrases
  that keyword search misses while preserving exact-term hits.

Retrieval **degrades cleanly**: with no embedder, no stored embeddings, or a
failed model call, search silently falls back to keyword-only — it never crashes
the loop.

```python
# Wire a model for semantic/hybrid search (Ollama-first; local + free):
from agent_os.providers import get_provider
ctx = ContextStore(embedder=get_provider("ollama:llama3").as_embedder())
ctx.reindex_embeddings()    # backfill a store that was keyword-only before
```

### 3. Grounding → context string + references

- `build_context(query, k, max_chars)` returns a single context string with each
  chunk tagged `[source: <name>]`, capped at `max_chars` — ready to feed an agent.
- `references(query, k)` returns the raw chunks as a list, ready to hand to Ninja
  Harness as the `references` of an `EvaluationCase`.

### 4. Scoring → the honesty gate

The router's `/ask` builds an `EvaluationCase(task=question, references=refs)`,
runs the answer through the agent, and scores the trajectory with Ninja Harness.
The **grounding** metric measures how well the answer is supported by the
retrieved sources; a weak answer is flagged (`WARN`/`FAIL`) instead of being
trusted. This is the difference between a chatbot and a brain you can rely on.

## The Ahaan example (end to end)

```bash
python examples/ahaan_maths_demo.py
```

Ahaan uploads his maths notes; the Brain ingests them; he asks "how do I add
fractions?"; the answer is composed **only from his notes**, tagged with their
source, and scored (`PASS · grounding 0.85`). Plug in a model
(`export AGENT_OS_PROVIDER=ollama:llama3`) and the answer becomes natural prose —
still grounded, still scored.

## Command surface

```bash
agent-os cmd "/learn ~/notes.md"          # ingest a file (or raw text)
agent-os cmd "/ask how do I add fractions?"   # grounded + scored answer
agent-os cmd "/model"                      # show the embedder/reasoner in use
```

## Schema

| table | columns | purpose |
|---|---|---|
| `docs` | `doc_id, source, title, created_at` | one row per ingested document |
| `chunks` | `chunk_id, doc_id, ordinal, text, source` | one row per paragraph-chunk |
| `embeddings` | `chunk_id, vec` (JSON) | one vector per chunk (only when an embedder is set) |

SQLite runs in WAL mode with a busy timeout so reads and writes don't block.

## The embedder contract

```python
Embedder = Callable[[list[str]], list[list[float]]]   # texts -> vectors
```

Any callable matching this works. [`providers.py`](providers.md) gives you one
from Ollama/OpenAI for free (`provider.as_embedder()`), but you can pass your own.

## Where this is going — from chunks to a graph

Flat chunks are the floor, not the ceiling. The next evolution of the Brain is a
**knowledge graph view**: entities and relationships extracted from your context,
explorable visually with guided tours and semantic search. We plan to draw on
[Understand-Anything](https://github.com/Lum1104/Understand-Anything) (a Claude
Code plugin that turns a codebase or knowledge base into an interactive knowledge
graph) — both as inspiration for a graph layer over the Brain and as a connector:
its `knowledge-graph.json` output can be **ingested into the Brain** so a
codebase's structure becomes part of your personal context, then surfaced in the
local UI (Module 3) and dashboards (Module 5). See the [roadmap](roadmap.md).
