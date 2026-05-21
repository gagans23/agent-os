---
name: gmail-digest
description: Read unread Gmail/inbox items and produce a concise digest (read-only).
triggers: [gmail, inbox, digest, unread, email summary]
expected_artifacts: [final.md, ninja_report.json]
risk: READ_ONLY
---

## Procedure
1. Authenticate with the user's Gmail credentials (operator profile).
2. List **only unread** items for the configured label.
3. Summarize sender + subject + one line each; leave bodies in the inbox.
4. This is **read-only** → it may run automatically.

## Pitfalls
- Reading is auto; **sending/replying is NOT** — a reply is a SEND action and
  requires approval.
- Do not expose full private email bodies beyond a brief summary.
- Summarize only unread items unless asked otherwise.

## Verification
- Risk classifier marks a pure digest READ_ONLY (auto-run).
- Any follow-up that sends an email is reclassified SEND → approval required.
