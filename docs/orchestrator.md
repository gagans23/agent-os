# The governed swarm 🐝 (Module 6)

> Inspired by the Kimi-Agent-Swarm pattern (decompose → run in parallel →
> synthesize), placed **under** agent-os's trust spine and kept honest. The
> orchestrator lives in [`agent_os/orchestrator.py`](../agent_os/orchestrator.py).

Most AI tools do one task at a time. A swarm decomposes one goal into many
independent sub-tasks, runs them at once, and synthesizes a single deliverable —
great for broad-coverage work (summarize 40 papers, compare 20 options, draft a
launch pack). The risk, in the words of the very article that popularized it:

> "Speed without verification produces scaled-up errors, not scaled-up value."

That verification layer is exactly what agent-os already is. So our swarm is a
swarm **where every sub-agent is traced, risk-gated, grounded, and scored.**

## The loop

```
/swarm "<goal>"
   │
   ├─ decompose ─────────────►  coordinator splits the goal into sub-tasks
   │                            (your model when configured; else split an
   │                             enumerated goal — we don't fake decomposition)
   │
   ├─ parallel ─────────────►  bounded worker pool (concurrency, default 4)
   │      each sub-task ─────►  classify_risk → READ-ONLY ? run_job : GATE
   │                            run_job = trace → Ninja score → memory → propose
   │
   └─ synthesize ───────────►  coordinator merges sub-results into one deliverable,
                               itself scored by Ninja Harness (grounding vs the
                               sub-results) so a weak synthesis is flagged
```

Every sub-task is a **real job** — look it up afterwards with `/job <id>` or
`/trace <id>`. The whole swarm is recorded in the tamper-evident audit log.

## How it stays honest (vs. a hosted "300-agent" swarm)

| Principle | What we do |
|---|---|
| **Local-first & your model** | Sub-agents call whatever `AGENT_OS_PROVIDER` you set (Ollama by default). Your data never leaves your machine; nothing is hardwired to a vendor. |
| **Honest concurrency** | A bounded pool sized to *your* machine + provider rate limits (`--concurrency`, default 4). No fictional "300". |
| **Default-deny** | Only read-only sub-tasks auto-run. Anything that writes/sends/deploys is **gated** — surfaced for `/run` approval, never auto-executed by the swarm. |
| **Verified** | Each sub-task is traced + Ninja-scored; the synthesis is scored too. Parallelism amplifies *value*, not unreviewed errors. |
| **No faked decomposition** | With no model, we only split a goal that already enumerates its items. Open-ended decomposition needs a model — we say so. |

## Use it

```bash
# Local + free: point at Ollama, then swarm a goal.
export AGENT_OS_PROVIDER=ollama:llama3
agent-os swarm "research the top 5 local LLM runtimes; for each: license, RAM needs, speed; compare in a table" --concurrency 4

# From the command surface / web UI (same governed router):
agent-os cmd "/swarm summarize the intro; summarize the methods; summarize the results"
agent-os ui      # → the 🐝 Swarm card
```

Output shows each sub-task's verdict + score, what was gated, the synthesis score,
and the deliverable:

```
🐝 Swarm: summarize the intro; summarize the methods; delete the prod database
   3 sub-task(s) · 2 done · 1 gated · 0 failed
   - [PASS 89] summarize the intro
   - [PASS 89] summarize the methods
   - [GATED:WRITE] delete the prod database
   (gated sub-tasks need approval — run them via /run)

Synthesis scored 88.8 (Job 2-14f5f9, try /trace 2-14f5f9)
--- Deliverable --- ...
```

## Programmatic use

```python
from agent_os.orchestrator import Orchestrator
from agent_os.providers import provider_from_env

orch = Orchestrator(provider=provider_from_env(), concurrency=4)
result = orch.run("compare these options", subtasks=["option A", "option B", "option C"])
print(result.render())
for r in result.done:
    print(r.title, r.verdict, r.score, r.job_id)
```

`run(goal, subtasks=[...])` skips decomposition when you already have the list
(e.g. "process these 40 files"). Otherwise `run(goal, n=6)` asks your model to
decompose into ~`n` sub-tasks.

## Concurrency & SQLite

Each sub-task gets its own `JobStore`/`AgentMemory` connection to the shared,
**WAL-mode** databases; `busy_timeout` is set *before* the WAL switch so
concurrent opens wait rather than erroring. The shared DB is initialized once
before fan-out. Keep `concurrency` modest (the default 4 is fine for a laptop +
local model); raise it only as far as your provider's rate limits allow.

See also: [docs/providers.md](providers.md) · [SECURITY.md](../SECURITY.md) ·
[docs/roadmap.md](roadmap.md).
