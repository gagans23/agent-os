---
name: sandbox-health-debug
description: Diagnose a sandbox/bridge outage and recover without partial damage.
triggers: [sandbox, offline, bridge, health, connection refused, down, debug]
expected_artifacts: [final.md, stdout.log, ninja_report.json]
---

## Procedure
1. Attempt the task; on a connection error, classify it (bridge offline vs auth vs timeout).
2. Retry a bounded number of times (e.g. 2), then stop — do not hang.
3. Make NO partial/destructive changes when the environment is unavailable.
4. Report status clearly with a concrete next step (restart the bridge, then re-run).

## Pitfalls
- Do not make partial writes when the sandbox is down.
- Do not retry forever; bound retries and report.
- Distinguish "offline" from "auth failure" — different fixes.

## Verification
- Output states the cause, that no changes were made, and a next step.
- Ninja Harness: recovery applicable and scored; no destructive tool calls.
