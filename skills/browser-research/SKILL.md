---
name: browser-research
description: Open pages, extract key facts, and report a concise evidence-based summary.
triggers: [browser, research, open, hacker news, website, scrape, summarize]
expected_artifacts: [final.md, screenshots, ninja_report.json]
---

## Procedure
1. Open the target page(s) (researcher profile, browser tool).
2. Extract the top items / key facts; save a screenshot.
3. Write a concise summary that states findings, not raw output.
4. Put raw headlines, links, and logs in a saved report artifact — not the answer.

## Pitfalls
- Do NOT dump raw headlines/logs/warnings into the final answer (output hygiene).
- Cite what was actually found; do not invent facts (grounding).
- Handle timeouts gracefully; never fabricate a metric a page failed to provide.

## Verification
- Final answer is concise and tied to references (Ninja grounding + output hygiene).
- Screenshot and report artifacts saved under the job's screenshots/ and final.md.
