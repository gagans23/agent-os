# agent-os roadmap — toward a personal agent OS

The end goal: **you click a button, agents come up, and they do the work** —
tracking, auditing, actioning, monitoring — grounded in your own context, with
every action traced, scored, and gated. A non-technical person should be able to
install it; a pro coder should be able to augment their work with it.

We build this **bit by bit, as modules** — never boiling the ocean.

## Where agent-os sits vs. Onyx

[Onyx](https://github.com/onyx-dot-app/onyx) is the open-source "application layer
for LLMs" — excellent agentic **RAG over 50+ connectors**, a polished UI, voice,
image-gen, multi-LLM. agent-os is **not** trying to out-connector Onyx. Our layer
is the **orchestration + evaluation + controlled-autonomy + personal-brain** spine:
every agent action is **traced → scored by [Ninja Harness](https://github.com/gagans23/ninja-harness) → risk-gated → improved**, which Onyx does not do. Heavy RAG can be
plugged in (even Onyx itself); the core stays local-first so a child can run it.

## Modules

| # | Module | Pillar | Status |
|---|---|---|---|
| 0 | **Trust & Governance** | track · audit · gate | ✅ memory, jobs, traces, skills, profiles, risk (default-deny + tool-aware), approvals, **tamper-evident audit**, eval gate, reliability/supervisor/health |
| 1 | **The Brain** 🧠 | self-aware context (your notes/files) | ✅ `context.py` ingest→retrieve, `/learn` `/ask`, grounded + scored (Ahaan-maths demo) |
| 2 | **Model onboarding** | plug Claude/OpenAI/Ollama/Replit | ✅ `providers.py` — Ollama-first, stdlib HTTP (no SDK), one env var (`AGENT_OS_PROVIDER`); powers reasoner/embedder/agent_fn; hybrid semantic search in the Brain; `/model` |
| 3 | **Easy install + UI** | "click a button"; non-technical install | next — one-command installer + minimal local web UI |
| 4 | **Pro-coder + connectors** | augment coders; ingest more sources | later — Claude Code/Cursor/Aider links, Onyx/MCP bridge |
| 5 | **Watchers + dashboards** | monitor your computer/thinking | later — folder/event watchers, trend dashboards |

## Principles

- **Local-first, dependency-light.** SQLite + stdlib core; heavy infra optional.
- **Pluggable, never faked.** You bring the model and the transports; agent-os
  ships the structure, gating, and scoring. No bundled keys, no hidden calls.
- **Default-deny autonomy.** Read-only auto-runs; anything ambiguous or that
  writes/sends/deploys needs human approval.
- **Everything leaves a trace, a score, and an improvement.** That's how it compounds.
