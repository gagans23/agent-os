---
name: podcast-digest
description: Summarize new podcast episodes and synthesize cross-episode insights with a delta vs the previous run.
triggers: [podcast, digest, episodes, feeds, cross-episode, insights]
expected_artifacts: [final.md, ninja_report.json]
risk: READ_ONLY
---

## Procedure
1. Sync feeds; fetch the latest **free** episodes (RSS / YouTube). Do NOT invoke
   paid providers automatically — that is a cost action and must be approved.
2. For each episode, produce a concise summary + key points (each point should be
   traceable to the episode, so claims can be grounded later).
3. Build `EpisodeSummary` objects and run `CrossEpisodeSynthesizer.synthesize(...)`
   with your LLM reasoner (the deterministic fallback only surfaces real overlap).
4. The synthesizer loads the previous digest from memory and computes the
   **delta vs previous state** (reinforced / new / shifted) — this is what makes
   the system compound.
5. Render the digest and report it. Evaluate it with Ninja Harness:
   - grounding → are insight claims supported by episode evidence?
   - output hygiene → is it concise, not a raw dump?

## Pitfalls
- Never fabricate quotes or claims; every claim must cite an episode.
- Mark paid vs free; never auto-invoke a paid provider (route through /approve).
- Keep the final report concise; raw transcripts/logs belong in artifacts.
- Don't overstate the delta — only call it "shifted" if the prior digest differs.

## Verification
- Each insight has evidence with a source episode.
- Ninja Harness: grounding passes (claims tied to references), output hygiene high.
- The digest is stored to memory so tomorrow's run can compute a delta.
