---
name: meeting-notes
description: Turn raw meeting notes or a transcript into a clean summary with decisions and action items.
triggers: [meeting, notes, transcript, minutes, standup, recap, action items]
---

## Procedure
1. Identify the meeting's purpose in one sentence.
2. Extract **Decisions** (what was agreed) as a bulleted list — only things
   actually decided, not options discussed.
3. Extract **Action items** as `owner — task — due` (use "unassigned" / "no date"
   when missing; never guess a name or date).
4. Extract **Open questions / risks** that were raised but not resolved.
5. Output in this order: one-line purpose, Decisions, Action items, Open
   questions. Keep it skimmable — no filler.

## Pitfalls
- Don't promote a discussion point to a "decision" unless it was clearly agreed.
- Don't assign owners or dates that weren't stated.
- Preserve names exactly as written; mark unclear attributions "[unclear]".

## Verification
- Every action item has an owner field and a due field (possibly "unassigned"/"no date").
- Decisions and open questions are disjoint (nothing appears in both).
- The summary is shorter than the source and invents no new facts.
