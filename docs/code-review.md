# Code review & engineering practices

> How we review changes across agent-os and
> [ninja-harness](https://github.com/gagans23/ninja-harness). "CL" below means a
> pull request / commit. These exist to keep one thing true over time: **the
> overall code health of the project improves with every change.**

## The standard

> **Approve a change once it *definitely improves the overall code health* of the
> system — even if it isn't perfect.**

This is the senior principle. There is no "perfect" code, only *better* code. A
reviewer should seek **continuous improvement**, not perfection, and should not
block a change that improves maintainability, readability, and understandability
over days of polishing. The mirror rule: **never merge a change that worsens
overall code health** (except a genuine emergency).

- **Technical facts and data overrule opinions and personal preferences.**
- **Design is not a style preference.** Weigh design on engineering principles. If
  several approaches are demonstrably equally valid, the author's choice wins.
- **Style is what the linter says.** Anything `ruff` doesn't cover is preference —
  stay consistent with the surrounding code.
- Use **"Nit:"** to mark a comment as optional polish the author may ignore.
- Teaching is welcome; mark purely educational comments as non-blocking.

## What to look for

When reviewing (or self-reviewing before you push), check:

- **Design** — does it fit the architecture? (router → risk gate → execute →
  trace → score; pluggable transports/models.)
- **Functionality** — does it do what's intended, and is that good for the user?
- **Complexity** — can it be simpler? Will the next person understand it?
- **Tests** — correct, well-designed, and **in the same change** (see below).
- **Naming / Comments** — clear names; comments explain *why*, not *what*.
- **Style** — `ruff check` is clean.
- **Docs** — README/`docs/` updated when behavior changes.
- **Safety (our addition)** — no secrets/keys committed; no faked external
  integrations; risk-gating and the audit chain still hold; SQLite stays WAL.
  See [SECURITY.md](../SECURITY.md).

## Speed & courtesy

- **Don't let changes sit.** Review within one business day; if you can't do a full
  review, send quick feedback or unblock the author.
- Comments are about the **code, not the coder.** Explain *why*; offer direction;
  prefer questions over commands when the path isn't certain.
- Resolve disagreements on **principles and data**; escalate rather than stall.

## For change authors

### Write small, self-contained changes

Small changes are reviewed faster and more thoroughly, introduce fewer bugs, and
are easier to roll back. Aim for **one self-contained change** that does *just one
thing*. ~100 lines is a comfortable size; ~1000 is usually too large. When in
doubt, make it smaller.

- **Separate refactors from behavior changes.** Move/rename in one change; fix the
  bug in another. (Tiny local cleanups can ride along.)
- **Keep related tests in the same change.** New/changed logic ships with new/updated
  tests; refactors keep existing tests green.
- **Don't break the build.** CI (`ruff` + `pytest`, plus the Ninja Harness eval
  gate) must be green for every change.

### Write good change descriptions

A commit/PR description is a permanent record. It must say **what** changed and
**why**.

- **First line:** a short, imperative summary that stands alone — "Add the `/model`
  command", not "Adding stuff". Then a blank line.
- **Body:** the problem, the approach and why it's the right one, any known
  shortcomings, and context (issue links, benchmarks). Even small changes deserve
  context.

Bad: `fix bug`, `add patch`, `phase 1`. Good:

> Add hybrid semantic search to the Brain.
>
> Embeddings are computed at ingest when a provider is configured; `search()`
> blends BM25 + cosine (min-max normalized) and degrades cleanly to keyword-only
> when no embedder is present. This catches paraphrases the keyword scorer missed
> without regressing exact-term hits.

### Handling review comments

Assume good intent, don't take it personally, and reply to every comment (resolve
or discuss). If you disagree, make the case with data or principles — and if it's
just a Nit, you're free to skip it.

## Our enforcement (already wired)

| Practice | How it's enforced |
|---|---|
| Don't break the build | `.github/workflows/ci.yml` — ruff + pytest on 3.11/3.12 + command smoke |
| Tests required | new logic lands with tests; CI fails otherwise |
| Style is the linter | `ruff check agent_os/ tests/ examples/` |
| Quality doesn't silently regress | every run is **scored by Ninja Harness**; weak runs are flagged |
| Good descriptions | `.github/PULL_REQUEST_TEMPLATE.md` |

See [CONTRIBUTING.md](../CONTRIBUTING.md) for setup and the day-to-day workflow.

<sub>Some wording draws on widely-used industry code-review guidance (incl. Google's, CC-BY 3.0).</sub>
