---
name: weekly-review
description: Run a weekly review from your notes and completed tasks into wins, misses, and next week's focus.
triggers: [weekly, review, retro, retrospective, planning, week, reflect]
---

## Procedure
1. Gather the inputs the user provides (done tasks, notes, recall of the week).
   If little is provided, ask for the week's notes rather than inventing activity.
2. Summarize **Wins** (what got done / went well) — concrete, with evidence.
3. Summarize **Misses / slipped** (what didn't happen and why, if stated).
4. Derive **Next week's focus**: at most 3 priorities, each a concrete outcome.
5. Note any **Recurring blocker** seen more than once — flag it explicitly.
6. Output: Wins, Misses, Top 3 focus, Recurring blockers. Keep each to a few lines.

## Pitfalls
- Don't fabricate accomplishments or metrics that aren't in the inputs.
- More than 3 priorities means none — force a ranked top 3.
- Distinguish "didn't finish" from "didn't start"; don't blur them.

## Verification
- Next-week focus has 3 or fewer items, each an outcome (not a vague theme).
- Every win/miss traces to something in the provided inputs.
