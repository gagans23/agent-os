# Contributing to agent-os

Thanks for your interest! agent-os is a self-improving agent platform that uses
[Ninja Harness](https://github.com/gagans23/ninja-harness) as its evaluation gate.
Contributions of all kinds are welcome — modules, skills, providers, docs, tests,
and bug fixes.

## Ground rules (please read)

These keep the project honest and aligned with the [roadmap](docs/roadmap.md):

- **Local-first, dependency-light.** SQLite + the standard library for the core.
  Heavy infrastructure is optional and pluggable — a non-technical person should
  be able to run agent-os with zero infra.
- **Pluggable, never faked.** You bring the model and the transports
  (WhatsApp/Meta, Gmail, Cloudflare, LLM providers). agent-os ships the structure,
  gating, and scoring — **no bundled API keys and no hidden network calls.**
- **Default-deny autonomy.** Read-only tasks may auto-run; anything ambiguous or
  that writes/sends/deploys must be risk-gated for human approval.
- **Everything leaves a trace, a score, and (if weak) an improvement.** Don't add
  paths that bypass the router, the audit log, or the eval gate.

## Development setup

Requires Python 3.11+.

```bash
./install.sh            # one command: local .venv + eval gate + agent-os
# or, manually:
python -m venv .venv && source .venv/bin/activate
pip install "ninja-harness @ git+https://github.com/gagans23/ninja-harness.git"
pip install -e ".[dev]"
```

## Before you open a PR

```bash
pytest -q                                   # all tests must pass
ruff check agent_os/ tests/ examples/       # lint must be clean
python -m compileall -q agent_os            # imports/syntax sanity
```

CI runs the same checks plus a command-surface smoke test on Python 3.11/3.12.

## How we work

We follow the practices in **[docs/code-review.md](docs/code-review.md)** (adapted
from Google's engineering practices). The short version:

- **Small, self-contained changes** that do one thing (~100 lines is comfortable).
- **Tests in the same change** as the logic they cover.
- **Separate refactors** from behavior changes.
- **Good descriptions:** an imperative first line that stands alone, a blank line,
  then a body explaining *why* (problem, approach, trade-offs, context).
- **Don't break the build** — keep CI (and the Ninja Harness eval gate) green.

## How to add things

### A new skill
Add `skills/<name>/SKILL.md` (triggers, procedure, pitfalls, verification,
artifacts). The registry loads it automatically; match a command to it in tests.

### A new model provider
Add a `Provider` subclass in `agent_os/providers.py` (`complete` + `embed`), keep
HTTP on the standard library, read keys from the environment (never bundle them),
register it in `_BUILDERS`, and add tests with a mocked transport. See
[docs/providers.md](docs/providers.md).

### A new command
Add a handler on `CommandRouter`, wire it into the dispatch table and `/help`, and
add a router test. Privileged actions must go through the risk classifier.

### A new module
Discuss it against the [roadmap](docs/roadmap.md) first (open an issue). Keep it
local-first and behind the traced → scored → gated spine.

## Commit & PR style

- **First line:** short, imperative, stands alone (e.g. "Add the `/model` command").
- **Body:** the *why* — problem, approach, trade-offs, context.
- Keep PRs focused; open an issue first for large changes.
- Update `docs/` and the README when behavior changes.
- AI-assisted commits include a `Co-Authored-By:` trailer for the assistant.

## Security

Don't commit secrets. For vulnerabilities, see [SECURITY.md](SECURITY.md) — do
**not** open a public issue.

By contributing, you agree your contributions are licensed under the project's
[Apache-2.0 license](LICENSE).
