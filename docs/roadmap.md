# agent-os roadmap — toward a personal agent OS

The end goal: **you click a button, agents come up, and they do the work** —
tracking, auditing, actioning, monitoring — grounded in your own context, with
every action traced, scored, and gated. A non-technical person should be able to
install it; a pro coder should be able to augment their work with it.

We build this **bit by bit, as modules** — never boiling the ocean.

## What agent-os is

agent-os is the **orchestration + evaluation + controlled-autonomy + personal-brain
spine** for your own agents. It isn't trying to be the biggest pile of connectors or
the flashiest chat UI; it's the layer that makes every agent action **traced →
scored by [Ninja Harness](https://github.com/gagans23/ninja-harness) → risk-gated →
improved**. The core stays **local-first** (SQLite + stdlib) so a non-technical
person can run it, and heavier retrieval/connectors can be plugged in behind the
same governed spine.

## Modules

| # | Module | Pillar | Status |
|---|---|---|---|
| 0 | **Trust & Governance** | track · audit · gate · cost | ✅ memory, jobs, traces, skills, profiles, risk (default-deny + tool-aware, **pluggable policy**), approvals, **tamper-evident audit**, eval gate, reliability/supervisor/health, **cost/latency/token metering** (`metering.py`, `/cost`), **composable hooks** (`hooks.py`, built-in secret redaction) |
| 1 | **The Brain** 🧠 | self-aware context (your notes/files) | ✅ `context.py` ingest→retrieve, `/learn` `/ask`, grounded + scored (Ahaan-maths demo) |
| 2 | **Model onboarding** | plug Claude/OpenAI/Ollama/Replit | ✅ `providers.py` — Ollama-first, stdlib HTTP (no SDK), one env var (`AGENT_OS_PROVIDER`); powers reasoner/embedder/agent_fn; hybrid semantic search in the Brain; `/model`; **`agent-os doctor`** hardware-aware model advisor (`doctor.py`) |
| 3 | **Easy install + UI** | "click a button"; non-technical install | ✅ `install.sh` one-command (local venv, no sudo) + `webui.py` minimal local web UI (`agent-os ui`, stdlib, localhost) over the same governed router |
| 4 | **Pro-coder + connectors** | augment coders; ingest more sources | 🚧 in progress — ✅ open `SKILL.md` compatibility (recursive/multi-root import via `AGENT_OS_SKILLS_PATH`, model-agnostic injection); next: MCP connector bridge, role packs, knowledge-graph import, coding-agent links |
| 5 | **Watchers + dashboards** | monitor your computer/thinking | later — folder/event watchers, trend dashboards, **knowledge-graph view of the Brain** |
| 6 | **The governed swarm** 🐝 | parallel scale, under the trust spine | ✅ `orchestrator.py` — decompose → bounded-parallel sub-jobs → synthesize; each sub-task traced + risk-gated (default-deny) + Ninja-scored; local-first, Ollama-testable, honest concurrency; `/swarm`, `agent-os swarm`, UI card. [deep dive](orchestrator.md) |

The deep dives: [the Brain](brain.md) · [model onboarding](providers.md) ·
[skills & Agent Skills](skills.md) · [install + UI](install-and-ui.md) ·
[cross-episode insights](insights.md) · [compose your own](extending.md) ·
[architecture](architecture.md).

## Planned capabilities

We don't reinvent what good open tools already do — we **mix them in** behind the
agent-os spine (traced → scored → gated), keeping the core local-first. Drawing
inspiration (not code) from the best open agent systems, the near-term targets are:

- **Knowledge-graph view of the Brain** — evolve from flat chunks (Module 1) to a
  navigable graph of entities/relationships, importable from a standard
  knowledge-graph export and surfaced in the UI (Module 3) and dashboards (Module 5).
  For Ahaan, his maths notes become a navigable map of concepts, not just search hits.
- **Open `SKILL.md` ecosystem** — ✅ already compatible with the open Agent Skills
  format; next, ship curated **role packs** (a non-technical "productivity" pack; a
  pro-coder dev pack) where every command runs through the governed router.
- **MCP connector bridge** — wire MCP connectors so skills/agents can reach real
  tools (model-agnostic, your credentials), behind the risk gate and audit log.
- **Pluggable heavy retrieval** — a richer RAG backend behind the Brain for users
  who want enterprise breadth, without changing the local-first default.

## Principles

- **Local-first, dependency-light.** SQLite + stdlib core; heavy infra optional.
- **Pluggable, never faked.** You bring the model and the transports; agent-os
  ships the structure, gating, and scoring. No bundled keys, no hidden calls.
- **Default-deny autonomy.** Read-only auto-runs; anything ambiguous or that
  writes/sends/deploys needs human approval.
- **Everything leaves a trace, a score, and an improvement.** That's how it compounds.
- **Mix in the best, don't reinvent.** Stand on solid open tools behind the
  orchestration + evaluation spine, instead of rebuilding them.
