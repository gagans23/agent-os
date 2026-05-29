# Compose your own agent-os

agent-os ships the **governed loop** — `command → profile → memory → skill →
execute → trace → score → propose → report` — with the risk gate, the
tamper-evident audit log, and the eval gate wired in. You extend it by composing
on top of that loop, **not by forking the runner**. Three seams make this clean:

1. **Providers** — bring your own model (Ollama, OpenAI, Anthropic, or your own).
2. **Hooks** — run before/after every agent call to layer in cross-cutting
   behavior (redaction, logging, custom metering).
3. **Policy** — swap the risk classifier for your own org rules without losing
   the gate.

Each seam keeps the governance guarantees intact: nothing you plug in can skip
the audit log, the risk gate, or the eval gate.

---

## 1. Providers — bring your own model

The model is never hardwired. Set one env var and every model-powered surface
(`/ask`, `/run`, `/digest`, the Brain's semantic search) uses it:

```bash
export AGENT_OS_PROVIDER=ollama:llama3              # local, no key, free
export AGENT_OS_PROVIDER=openai:gpt-4o-mini         # needs OPENAI_API_KEY
export AGENT_OS_PROVIDER=anthropic:claude-3-5-sonnet-20241022
```

With none configured, agent-os stays deterministic and makes **no** model calls.
To wire a model in code, implement the `Provider` ABC (`complete` / `embed`) and
pass it: `CommandRouter(provider=MyProvider())`. See [providers.md](providers.md).

---

## 2. Hooks — compose behavior around every action

A **hook** is a small callable that runs around every job, in two phases:

- **BEFORE** — after context is assembled, before the agent runs. May rewrite the
  context the agent sees.
- **AFTER** — after the agent returns, before the output is traced/scored. May
  rewrite the final output.

Hooks run *inside* the governed loop — they never bypass the gate, the audit log,
or the eval gate. A failing hook is isolated (its error is recorded in
`ctx.meta['hook_errors']`) so one bad hook can't break a job.

### Built-in: redaction (on by default)

The default registry redacts common secrets (API keys, bearer tokens, emails)
from both the context the model sees and the output it produces — defense in
depth, so nothing privileged leaks into the trace, the eval gate, or a transport.

```python
from agent_os import HookRegistry, run_job

# Default registry = redaction on. This is what run_job uses when you pass nothing.
run_job("summarize the research", my_agent)   # redaction applied automatically
```

### Write your own hook

A hook is `Callable[[HookContext], None]` — mutate the context in place:

```python
from agent_os import HookRegistry, HookPhase, run_job

def audit_size(ctx):
    if ctx.phase is HookPhase.AFTER and ctx.output:
        ctx.meta.setdefault("metrics", {})["chars"] = len(ctx.output)

def to_upper_context(ctx):
    if ctx.phase is HookPhase.BEFORE:
        ctx.context = ctx.context.upper()

reg = HookRegistry.default()        # start from redaction…
reg.add_after(audit_size, name="size")          # …and compose more
reg.add_before(to_upper_context, name="shout")

run_job("summarize the research", my_agent, hooks=reg)
```

Pass `hooks=` to `CommandRouter(...)` to apply your registry to every `/run`,
`/ask`, and swarm sub-job. Pass `hooks=HookRegistry()` (empty) to opt out of the
built-in redaction — not recommended.

---

## 3. Policy — swap the risk classifier, keep the gate

The default risk policy is **default-deny + tool-aware**: read-only tasks
auto-run, anything that writes/sends/deploys (or is ambiguous) needs human
approval. You can replace the classifier with your own org rules — the gate still
runs every time, and approvals/audit are unchanged.

A policy is any `callable(command, tools=None) -> RiskAssessment`:

```python
from agent_os import CommandRouter, RiskAssessment, RiskLevel

def my_policy(command, tools=None):
    # Example: everything touching "prod" is DEPLOY-risk, no matter the wording.
    if "prod" in command.lower():
        return RiskAssessment(level=RiskLevel.DEPLOY, requires_approval=True,
                              reason="org policy: prod changes need approval")
    from agent_os import classify_risk
    return classify_risk(command, tools)        # fall back to the default

router = CommandRouter(policy=my_policy)
```

The router uses `self.policy` for both `/run` (the gate) and `/risk` (the
explainer), so your rules are reflected consistently.

> An LLM-based classifier can be layered on top here too — but keep the
> conservative deterministic baseline as the fallback so a model outage can never
> silently auto-run a destructive action.

---

## What you **cannot** bypass

These are deliberate — composability never opens a hole in governance:

- Every command is **audited** (hash-chained, tamper-evident).
- Every privileged action is **gated** (default-deny on ambiguity).
- Every job is **traced and scored** by the eval gate.

Plug in models, hooks, and policy freely; the trust spine stays intact.
