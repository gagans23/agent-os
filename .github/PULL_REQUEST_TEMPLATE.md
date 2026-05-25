<!-- Thanks for contributing to agent-os! See CONTRIBUTING.md and docs/code-review.md. -->

## Summary

<!-- First line: a short, imperative summary that stands alone (e.g. "Add the /model command"). -->

## Why

<!-- The problem this solves, the approach and why it's right, any trade-offs, and context (issue links, benchmarks). Even small changes deserve context. -->

## Type of change

- [ ] Bug fix
- [ ] New module / command
- [ ] New skill
- [ ] New model provider
- [ ] Docs
- [ ] Tooling / CI
- [ ] Other

## Test plan

<!-- How you verified this. Paste key output if useful. -->

## Checklist

- [ ] Small and self-contained — does one thing
- [ ] Refactors are separated from behavior changes
- [ ] `pytest -q` passes; added/updated tests for new behavior
- [ ] `ruff check agent_os/ tests/ examples/` is clean
- [ ] Updated `docs/` and `README.md` if behavior changed
- [ ] Local-first & pluggable: no bundled keys, no hidden network calls, no faked integrations
- [ ] Privileged actions (write/send/deploy) stay risk-gated; nothing bypasses the router/audit/eval gate

## Notes for reviewers

<!-- Anything specific you'd like feedback on -->
