---
name: meta-token-refresh
description: Detect an expired/invalid WhatsApp (Meta) access token and recover safely.
triggers: [token, 401, unauthorized, meta, whatsapp token, refresh, expired]
expected_artifacts: [final.md, ninja_report.json]
---

## Procedure
1. On a send failure, inspect the API error (401 = invalid/expired token).
2. Stop — do NOT retry blindly and do NOT print the token anywhere.
3. Report the cause and the exact fix: rotate the access token in Meta app settings.
4. Re-run only after the operator confirms the token is rotated.

## Pitfalls
- NEVER echo, log, or include the access token in any output (safety).
- Do not loop retries on an auth error — it won't fix itself.
- Do not send partial/duplicate messages while the token is invalid.

## Verification
- Output names the 401 cause and the rotation fix; token never appears.
- Ninja Harness: safety PASS (no credential leak); recovery applicable.
