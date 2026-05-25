# Security Policy

agent-os takes real-world actions on a user's behalf, so security is a
first-class concern, not an afterthought.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.** Report privately via
GitHub's [Report a vulnerability](https://github.com/gagans23/agent-os/security/advisories/new)
or contact the maintainer directly. Please include repro steps and the version.

## Threat model

agent-os is a runtime that can route commands to agents which read data, send
messages, write files, and deploy. The controls that keep that safe:

| Threat | Control |
|---|---|
| Unauthorized commands (spoofed sender) | **Allowlist, fail-closed** (`allowlist.py`) — an empty allowlist denies everyone; senders are normalized before matching. |
| Destructive action auto-runs | **Risk classifier with default-deny** (`risk.py`) — read-only auto-runs; write/send/deploy **and ambiguous** tasks require human approval. Tool capability escalates risk regardless of wording. |
| Privileged action without consent | **Approval queue** (`approvals.py`) — `/approve` / `/reject`; nothing privileged executes without an explicit decision. |
| Repudiation / "who did what" | **Tamper-evident audit log** (`audit.py`) — every command + decision is hash-chained; `verify()` detects any insertion/edit/deletion. |
| Secret leakage | Tokens are read from the environment, never bundled or logged; `token_health.py` checks presence/shape **without** returning the value. |
| Untrusted agent code | Run agents inside a sandbox (Ninja Harness `DockerSandbox` for isolation; `LocalSandbox` does **not** isolate from the host). |
| Crash / DoS | Process **supervisor** with bounded restarts + backoff; **timeouts** on subprocess calls; SQLite **WAL + busy_timeout**. |
| Silent quality regression | Every action is **scored by Ninja Harness**; weak runs are flagged and produce a propose-only improvement (never auto-applied). |
| Handler errors leaking internals | Router **error boundary** returns a friendly message and audits the error — no stack traces to the user. |
| Web UI exposure | `agent-os ui` binds to **127.0.0.1** (localhost) with **no built-in auth**; it drives the same governed router (audit + risk gating still apply). Do not bind it to a public address without your own auth/TLS in front. |

## Known limitations (be aware)

- The risk classifier is deterministic/heuristic. It is **conservative** (defaults
  to requiring approval when unsure) but should be paired with the approval gate,
  not trusted alone. An LLM classifier can be layered on top.
- `LocalSandbox` is convenience, not isolation. Use `DockerSandbox` for untrusted code.
- Live transports (WhatsApp/Meta, Gmail, Cloudflare) are **your** integrations —
  apply your own auth, rate limiting, and secret management at that boundary.
- Insight/RAG reasoning sends your content to whatever model you wire in. Review
  your provider's data policy; agent-os makes no calls you didn't configure.

## Responsible use

agent-os is for augmenting your own work and systems with your authorization. Do
not use it to act on systems or accounts you are not authorized to control.
