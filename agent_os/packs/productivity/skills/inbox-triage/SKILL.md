---
name: inbox-triage
description: Triage a batch of emails or messages into clear actions without drafting or sending anything.
triggers: [inbox, email, triage, unread, messages, sort, prioritize]
---

## Procedure
1. Read each item and classify it as exactly one of: **Reply needed**,
   **Read-only / FYI**, **Action (task)**, **Waiting on someone**, or **Archive**.
2. For "Reply needed", capture the one-line gist and the decision the reply must
   make — do **not** draft the reply here.
3. For "Action", extract a concrete task (verb + object + owner + due date if any).
4. Produce a single triage summary, grouped by category, newest first, with the
   sender and a ≤12-word gist per item. Put counts at the top.
5. End with a short "Top 3 to handle first" list, chosen by deadline then sender
   importance.

## Pitfalls
- Never send, reply, archive, or mark items read — triage is read-only. Any
  send/delete is a separate, explicitly-approved action.
- Don't invent deadlines or commitments that aren't in the text.
- Keep sensitive content (codes, passwords) out of the summary; reference it as
  "[sensitive]".

## Verification
- Every input item appears in exactly one category.
- Counts at the top equal the number of items listed.
- No drafted replies and no actions taken — only a summary.
