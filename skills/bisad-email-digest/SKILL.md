---
name: bisad-email-digest
description: Summarize ONLY new (unread) BISAD school inbox items.
triggers: [bisad, email, inbox, digest, unread, gmail]
expected_artifacts: [final.md, ninja_report.json]
---

## Procedure
1. Authenticate to the configured Gmail/inbox account (operator profile).
2. List **only unread** messages for the BISAD label — never the whole inbox.
3. For each, capture sender, subject, and a one-line summary.
4. Produce a concise digest; leave full email bodies in the inbox.

## Pitfalls
- Do NOT dump full email bodies — summarize only.
- Do NOT include already-read items; "new" means unread.
- Avoid leaking other recipients' personal data.

## Verification
- Output lists only unread items with counts.
- No raw email bodies in the final answer.
- Ninja Harness: grounding references match the listed items; safety PASS.
