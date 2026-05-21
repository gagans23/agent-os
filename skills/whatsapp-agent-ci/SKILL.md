---
name: whatsapp-agent-ci
description: Run a task, evaluate it with Ninja Harness, and report PASS/WARN/FAIL to WhatsApp.
triggers: [eval, whatsapp, ci, report, status, run task]
expected_artifacts: [trace.json, ninja_report.json, final.md]
---

## Procedure
1. Execute the task; record the trajectory via the trace recorder.
2. Run Ninja Harness on the saved trace (optionally against an eval case).
3. If NARI score < the profile threshold, mark WARN and build an improvement proposal.
4. Send a compact WhatsApp summary (result, score, safety, weakness, artifact).

## Pitfalls
- Send only to the authorized recipient; never duplicate messages.
- Never include secrets/tokens in the WhatsApp message.
- Do not auto-apply improvement proposals — they require human approval.

## Verification
- WhatsApp summary matches the saved ninja_report.json.
- Exit code is non-zero when the run is flagged (so CI can gate).
- Delivery confirmed; no duplicate sends.
