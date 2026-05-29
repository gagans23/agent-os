# CLAUDE.md — agent-os

Context for Claude Code sessions working on this repository.

## Project

agent-os is a self-improving agent **platform/runtime**. A command flows:
`command → profile → memory → skill → execute → trace → evaluate → propose
improvement → report`. It uses [Ninja Harness](https://github.com/gagans23/ninja-harness)
as its **evaluation gate** (kept as a separate project on purpose: one runs
agents, the other grades them).

## Stack

- Python 3.11+
- Standard library + **SQLite** for the core (WAL mode). No heavy runtime deps.
- `argparse` CLI (`cli.py`), stdlib `http.server` web UI (`webui.py`)
- PyYAML for eval cases; `ninja-harness` as the eval gate
- Pytest + Ruff for tests/lint

## Coding rules

1. **Local-first, dependency-light.** SQLite + stdlib for the core; heavy infra is
   optional and pluggable. Don't add a required third-party runtime dependency
   without a strong reason.
2. **Pluggable, never faked.** No bundled API keys, no hidden network calls, no
   stubs that pretend to call WhatsApp/Meta/Gmail/Cloudflare or an LLM. Models and
   transports are user-supplied (see `providers.py`).
3. **Default-deny autonomy.** Read-only may auto-run; ambiguous or
   write/send/deploy tasks must be risk-gated for approval (`risk.py`,
   `approvals.py`). Nothing privileged bypasses the gate.
4. **Everything is traced, scored, and (if weak) improved.** Don't add paths that
   skip the router, the tamper-evident audit log (`audit.py`), or the eval gate.
5. **SQLite stores** open with `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000`.
6. Type hints everywhere. No secrets in the codebase.
7. Run `ruff check agent_os/ tests/ examples/` and `pytest -q` before finalizing.
8. **Small, self-contained changes** with tests in the same change; refactors
   separate from behavior changes. Imperative first-line commit summaries + a
   *why* body. See `docs/code-review.md` and `CONTRIBUTING.md`.

## Directory layout

```
agent_os/
  __init__.py        — version + public re-exports
  cli.py             — argparse CLI (run/cmd/ui/skills/memory/health/...)
  command_router.py  — transport-agnostic command surface (returns plain text)
  webui.py           — stdlib local web UI (Module 3)
  context.py         — the Brain: knowledge base + BM25/hybrid retrieval (Module 1)
  providers.py       — model onboarding: Ollama/OpenAI/Anthropic/Echo (Module 2)
  risk.py            — risk classifier (default-deny + tool-aware); pluggable via CommandRouter(policy=…)
  hooks.py           — composable before/after-action hooks (built-in redaction) — see docs/extending.md
  approvals.py       — approval queue
  audit.py           — hash-chained tamper-evident audit log
  jobs.py            — SQLite job store
  runner.py          — the loop (execute → trace → Ninja eval → propose)
  trace_recorder.py  — per-job trace artifacts
  agent_memory.py    — persistent memory (MEMORY/USER/state.db/sessions)
  skill_registry.py  — load skills from skills/*/SKILL.md
  profiles.py        — researcher/operator/builder/qa
  orchestrator.py    — the governed swarm: decompose → parallel → synthesize (Module 6)
  doctor.py          — hardware-aware model advisor (`agent-os doctor`, `/doctor`)
  metering.py        — cost/latency/token accounting (`/cost`); est. tokens + pricing table
  insights.py / reasoners.py — cross-episode digest + LLM reasoner adapter
  improvement.py     — propose-only improvement proposals
  supervisor.py / health.py / reliability.py / token_health.py / allowlist.py / daily_eval.py
```

## Running locally

```bash
pip install -e ".[dev]"
agent-os cmd "/ping"
agent-os ui                 # local web UI at http://127.0.0.1:8765
python examples/ahaan_maths_demo.py
```

## Modules / status (see docs/roadmap.md)

- **0 Trust & Governance** ✅ — risk default-deny + tool-aware, hash-chained audit,
  approvals, WAL, supervisor/health, CI, SECURITY.
- **1 The Brain** ✅ — `context.py`, `/learn` `/ask`, grounded + scored; hybrid
  semantic search when an embedder is configured.
- **2 Model onboarding** ✅ — `providers.py`, one env var (`AGENT_OS_PROVIDER`),
  Ollama-first, stdlib HTTP, powers reasoner/embedder/agent_fn; `/model`.
- **3 Easy install + UI** ✅ — `install.sh` + `webui.py` (`agent-os ui`).
- **4 Pro-coder + connectors** — 🚧 ✅ open `SKILL.md` compatibility (import via
  `AGENT_OS_SKILLS_PATH`, recursive/multi-root, model-agnostic injection); next:
  MCP connector bridge, role packs, knowledge-graph import into the Brain,
  coding-agent links. See docs/roadmap.md → Planned capabilities.
- **5 Watchers + dashboards** — later: folder/event watchers, trend dashboards,
  knowledge-graph view of the Brain.
- **6 The governed swarm** ✅ — `orchestrator.py`: decompose → bounded-parallel
  sub-jobs → synthesize. Each sub-task is traced + risk-gated (default-deny:
  privileged sub-tasks are gated, never auto-run) + Ninja-scored; synthesis scored
  too. Local-first, Ollama-testable, honest concurrency (no fake "300"). `/swarm`,
  `agent-os swarm`, UI card. Per-worker WAL connections (busy_timeout before WAL).
  See docs/orchestrator.md.

## Boundaries I cannot cross for the user

Set up Cloudflare/Meta/Gmail accounts, publish to PyPI, or post to social media —
those need the user's own credentials/accounts. Build the structure; leave the
live wiring to the user.
