---
name: github-publish
description: Commit and publish changes to GitHub (push / release).
triggers: [github, publish, push, release, commit, deploy, ship]
expected_artifacts: [final.md, ninja_report.json]
risk: DEPLOY
---

## Procedure
1. Stage only the intended files (never `git add -A` blindly; never stage secrets).
2. Run tests / Ninja Harness; do not publish on a failing eval.
3. Open the diff for review.
4. **Requires approval** — this is a DEPLOY action. The platform enqueues it and
   waits for `/approve <id>` before pushing/releasing.
5. On approval, push and (optionally) create a release with notes.

## Pitfalls
- Never force-push to main or push secrets.
- Never publish when the eval gate is WARN/FAIL without explicit approval.
- Use the user's `gh`/git credentials — agent-os does not embed tokens.

## Verification
- Risk classifier marks this DEPLOY → approval required (no auto-run).
- After approval, the push/release succeeds and a trace + score are recorded.
