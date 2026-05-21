# agent-os

**A self-improving agent platform that uses [Ninja Harness](https://github.com/gagans23/ninja-harness) as its evaluation gate.**

agent-os is the *runtime* layer — command routing, agent profiles, persistent
memory, a reusable skill library, full trace recording, and a propose-only
self-improvement loop. Ninja Harness is the *evaluation/certification* layer it
calls. Keeping them separate is deliberate: one runs agents, the other grades them.

```
command → profile → memory → skill → execute → trace → Ninja Harness eval
        → propose improvement (human-approved) → report
```

> Status: **v0.1 scaffold.** Core modules + the run→eval→propose loop are working.
> Live integrations (WhatsApp/Meta, Gmail, Cloudflare Tunnel) are pluggable
> adapters you wire with your own credentials — none are bundled or faked.

## Install

Requires Python 3.11+ and a local Ninja Harness checkout (until it's on PyPI):

```bash
pip install -e ../ninja-harness    # the eval gate
pip install -e ".[dev]"            # agent-os
```

## Try the loop (no external services)

```bash
python examples/demo_run.py
# or
agent-os run "research the top Hacker News stories" --profile researcher
```

Example output:

```
Job complete.

Result: PASS
Ninja score: 94.3
Safety: PASS
Artifact: traces/<job_id>/final.md
```

## The three core modules

| Module | Responsibility |
|---|---|
| `trace_recorder.py` | Record every job into `traces/<job_id>/` (command, stdout, screenshots, final, trace.json, ninja_report.json). Produces a Ninja-Harness-parseable trace. |
| `agent_memory.py` | Persistent memory: `MEMORY.md`, `USER.md`, `state.db` (facts, prefs, outcomes), `sessions/`. |
| `skill_registry.py` | Load reusable procedures from `skills/*/SKILL.md` (triggers, procedure, pitfalls, verification, artifacts) and match a command to the best skill. |

Plus: `profiles.py` (researcher / operator / builder / qa), `improvement.py`
(propose-only patches), and `runner.py` (the loop).

## Agent profiles

Each profile has its own allowed tools, memory namespace, personality, and a
quality threshold for the eval gate:

- **researcher** — browser + summarization (threshold 85)
- **operator** — Gmail, WhatsApp, status checks (threshold 90; touches secrets)
- **builder** — code changes, GitHub, deployments (threshold 85)
- **qa** — Ninja Harness, regression, red-team (threshold 80)

## Self-improvement (propose-only)

After a weak run (`NARI < profile threshold`), `propose_improvement()` builds a
structured proposal — failure reason, suggested memory update, suggested skill
patch — that **requires explicit human approval**. The agent never rewrites
itself automatically.

## CLI

```bash
agent-os run "<command>" [--profile P] [--agent-cmd "python my_agent.py"] [--case case.yaml] [--json]
agent-os skills      # list skills + triggers
agent-os memory      # recent job outcomes
```

`agent-os run` exits non-zero when a run is flagged, so it works as a CI gate.

## Roadmap

- v0.1 (this scaffold): core modules + run→eval→propose loop ✅
- Next: production reliability (SQLite job persistence, webhook HMAC verification,
  sender allowlist, audit logs, retry/timeout, daily eval, secrets-excluding
  GitHub backup), then live WhatsApp/Gmail/Cloudflare adapters.

## License

Apache-2.0.
