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
| 3 | **Easy install + UI** | "click a button"; non-technical install | ✅ `install.sh` one-command (local venv, no sudo) + `webui.py` minimal local web UI (`agent-os ui`, stdlib, localhost) over the same governed router |
| 4 | **Pro-coder + connectors** | augment coders; ingest more sources | later — Claude Code/Cursor/Aider links, Onyx/MCP bridge, Understand-Anything graph import, **Agent Skills** import, **knowledge-work plugin** bundles |
| 5 | **Watchers + dashboards** | monitor your computer/thinking | later — folder/event watchers, trend dashboards, **knowledge-graph view of the Brain** |

The deep dives: [the Brain](brain.md) · [model onboarding](providers.md) ·
[cross-episode insights](insights.md) · [architecture](architecture.md).

## Planned integrations

We don't reinvent what great open tools already do — we **mix them in** behind the
agent-os spine (traced → scored → gated), keeping the core local-first.

- **[Understand-Anything](https://github.com/Lum1104/Understand-Anything)** (MIT) —
  a Claude Code plugin that turns any codebase/knowledge base/docs into an
  **interactive knowledge graph** (multi-agent pipeline → files/functions/concepts
  as nodes + relationships; guided tours, fuzzy + semantic search, diff-impact
  analysis, a visual dashboard). This is the natural **graph + visual view of the
  Brain** — the evolution from flat chunks (Module 1) to a navigable concept graph.
  Plan: (a) **import** its `.understand-anything/knowledge-graph.json` into the
  Brain so a codebase's structure becomes part of your personal context; (b) build
  a **graph layer over the Brain** (entities/edges/communities) inspired by it;
  (c) surface that graph in the local UI (Module 3) and dashboards (Module 5).
  For Ahaan, his maths notes become a navigable map of concepts, not just search
  hits. *Use when Modules 3–5 land.*
- **[Agent Skills](https://github.com/anthropics/skills)** (Apache-2.0; spec at
  [agentskills.io](https://agentskills.io)) — skills are self-contained `SKILL.md`
  folders (YAML `name`/`description` + instructions/scripts/resources) Claude loads
  dynamically. This is the **same shape as agent-os's `skill_registry.py`**
  (`skills/*/SKILL.md`). Plan: (a) **align our SKILL.md with the Agent Skills spec**
  so skills are portable in/out of Claude Code/Cowork; (b) **import** the open-source
  skills (docx/pdf/pptx/xlsx, testing, MCP-gen, …) into our registry, each invoked
  **through the governed router** (risk-gated, audited, scored). *Use when Module 4
  lands — strengthens Module 0 skills too.*
- **[Knowledge-Work Plugins](https://github.com/anthropics/knowledge-work-plugins)** —
  11 role bundles (productivity, sales, support, PM, marketing, legal, finance,
  data, enterprise-search, bio-research) for Claude Cowork/Code; each is file-based:
  `commands/` (slash commands) + `skills/` + `.mcp.json` (MCP connectors). Plan:
  (a) **bridge `.mcp.json` connectors** via the Module 4 MCP bridge; (b) adopt the
  **bundle structure** to ship agent-os **role packs** (a non-technical person picks
  "productivity"; a pro coder picks a dev pack) where every command runs through the
  traced → scored → gated spine; (c) reuse their skills via the Agent Skills import
  above. *Use when Module 4 (connectors) and Module 5 (dashboards) land.*
- **[Onyx](https://github.com/onyx-dot-app/onyx)** — heavy agentic RAG over 50+
  connectors, pluggable as a retrieval backend behind the Brain when a user wants
  enterprise breadth (Module 4).

## Principles

- **Local-first, dependency-light.** SQLite + stdlib core; heavy infra optional.
- **Pluggable, never faked.** You bring the model and the transports; agent-os
  ships the structure, gating, and scoring. No bundled keys, no hidden calls.
- **Default-deny autonomy.** Read-only auto-runs; anything ambiguous or that
  writes/sends/deploys needs human approval.
- **Everything leaves a trace, a score, and an improvement.** That's how it compounds.
- **Mix in the best, don't reinvent.** Stand on great open tools (Understand-Anything,
  Onyx, Ollama) behind the orchestration + evaluation spine, instead of rebuilding them.
