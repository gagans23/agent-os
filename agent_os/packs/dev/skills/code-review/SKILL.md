---
name: code-review
description: Review a code diff for correctness bugs, then reuse/simplification cleanups, with file:line references.
triggers: [code, review, diff, pr, pull request, changes, critique]
---

## Procedure
1. Read the diff and restate, in one sentence, what change it makes.
2. Pass 1 — **Correctness**: look for logic errors, off-by-one, null/None and
   error handling, race conditions, resource leaks, and broken invariants. Cite
   each finding as `path:line` with a one-line why and a concrete fix.
3. Pass 2 — **Reuse / simplification / efficiency**: duplicated logic, a stdlib
   or existing helper that already does this, needless complexity, obvious
   inefficiency. Only flag changes that clearly improve the code.
4. Rank findings by severity: **blocker → should-fix → nit**.
5. End with a one-line verdict: approve, approve-with-nits, or request-changes.

## Pitfalls
- Don't rewrite the whole file; comment on the diff and adjacent context only.
- No style nits a formatter/linter would catch — focus on substance.
- Don't claim a bug without the path:line and a reason; mark guesses "uncertain".
- Read-only: propose fixes, do not apply them here.

## Verification
- Every finding has a `path:line` and a severity.
- Findings are real (correctness or a concrete improvement), not speculation.
- The review ends with one clear verdict.
