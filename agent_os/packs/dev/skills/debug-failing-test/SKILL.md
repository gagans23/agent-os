---
name: debug-failing-test
description: Diagnose a failing test from its output and propose the smallest fix, root cause first.
triggers: [debug, failing, test, error, traceback, stacktrace, bug, broken]
---

## Procedure
1. Read the failure output and quote the exact assertion or exception + the
   `file:line` where it originates.
2. State the **observed vs. expected** behavior in one line each.
3. Form the most likely **root cause** hypothesis; note 1–2 alternates if unsure.
4. Decide whether the bug is in the **test** or the **code under test** — justify.
5. Propose the **smallest** change that fixes the root cause (not the symptom),
   as a diff or precise edit with `path:line`.
6. State how to confirm: the exact command to re-run, and what output proves it fixed.

## Pitfalls
- Don't "fix" by loosening the assertion unless the test itself is wrong — say so explicitly.
- Don't fix the symptom (e.g. catch-and-ignore) when the root cause is reachable.
- If the cause is genuinely unclear, say what extra signal (a log/print, a re-run)
  you'd add — don't guess silently.

## Verification
- The proposed fix targets the stated root cause, not just the failing line.
- A concrete re-run command + expected passing output is given.
- The change is minimal and scoped to the cause.
