# Skills — and Agent Skills compatibility 🧩

> Module 4 (first slice). `agent_os/skill_registry.py`. Skills are reusable
> procedures the agent reads; the runner matches one to a command and injects it
> into the agent's context — **through whatever model you configured (Ollama,
> OpenAI, …), never hardwired to one vendor.**

## Two formats, auto-detected

**agent-os format** — explicit `triggers` for deterministic matching + sections:

```markdown
---
name: browser-research
description: Open pages, extract key facts, report a concise summary.
triggers: [browser, research, open, scrape, summarize]
expected_artifacts: [final.md, ninja_report.json]
---
## Procedure
1. ...
## Pitfalls
- ...
## Verification
- ...
```

**[Agent Skills](https://agentskills.io) standard** — the open `SKILL.md` format.
Only `name` + `description` are required; the whole body is the instruction set:

```markdown
---
name: pdf
description: Extract text and tables from PDF files and fill PDF forms.
license: Apache-2.0
allowed-tools: [Read, Bash]
---
# PDF skill
Use pdfplumber to extract text, then fill the requested form fields.
```

For Agent Skills we **derive trigger keywords from the name + description** (so the
deterministic matcher still works) and treat the whole body as the procedure.
`allowed-tools` is captured. Your existing agent-os skills are unchanged.

## Importing an open Agent Skills tree

Skills are just markdown — point at any folder of open `SKILL.md` skills, no code:

```bash
export AGENT_OS_SKILLS_PATH="/path/to/skills"        # os.pathsep-separated for many
agent-os cmd "/skills"                                # your skills + the imported ones
```

Discovery is **recursive** (`**/SKILL.md`), so nested trees — categories
(`skills/<category>/<skill>/SKILL.md`) or a plugin's `skills/` folder — are all
picked up. When a name collides across roots, **your local skill wins**.

## How a skill reaches the model (and why it's vendor-neutral)

```
command ──> SkillRegistry.match() ──> runner injects skill into `context`
                                           │
                                           ▼
                         agent_fn(command, context, job)
                                           │
              provider.as_agent_fn(): prompt = context + task ──> provider.complete()
```

The runner adds the matched skill's instructions to the context string, and the
provider folds that context into the prompt it sends to **your** model. Swap the
model with one env var — nothing in the skill path is Claude-specific:

```bash
export AGENT_OS_PROVIDER=ollama:llama3      # local + free; test it here
export AGENT_OS_PROVIDER=openai:gpt-4o-mini
# (unset) → deterministic mode, still matches/records the skill
```

Privileged tasks still pass through the **risk gate** and the **audit log**, and the
result is **scored by Ninja Harness** — importing a skill doesn't bypass governance.

## Authoring a skill

Drop a folder with a `SKILL.md` under `skills/` (or any `AGENT_OS_SKILLS_PATH`
root). Use either format. Minimum: `name` + `description`. Add `triggers` if you
want precise control over when it fires; otherwise they're derived.

## What's next in Module 4

- **MCP connector bridge** — wire MCP (`.mcp.json`) connectors so skills can reach
  real tools (model-agnostic, your credentials).
- **Role packs** — a plugin-bundle shape (`commands/` + `skills/`) to ship curated
  packs (a non-technical "productivity" pack; a pro-coder dev pack).
- **Knowledge-graph import** into the Brain. See [roadmap](roadmap.md).
