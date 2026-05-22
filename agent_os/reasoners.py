"""
reasoners — adapters that turn episode summaries (+ prior insights) into Insights.

A `reasoner` has the signature ``(episodes, previous) -> list[Insight]``. The
default `keyword_reasoner` (in insights.py) is deterministic. `LLMReasoner` shows
how to plug in YOUR model:

    from agent_os.reasoners import LLMReasoner
    from agent_os.insights import CrossEpisodeSynthesizer

    def complete(prompt: str) -> str:
        return my_llm_client.generate(prompt)   # your model — anthropic/openai/local

    synth = CrossEpisodeSynthesizer(reasoner=LLMReasoner(complete), memory=mem)

No model is bundled or called here. `LLMReasoner` only (1) builds a structured,
grounding-aware prompt and (2) parses the model's JSON reply into Insight objects.
The model call is the `complete` callable you supply.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from agent_os.insights import EpisodeSummary, Insight

# Your model client, wrapped as: prompt -> completion text.
Complete = Callable[[str], str]

_INSTRUCTIONS = """You synthesize cross-episode insights from the episodes below.

Rules:
- Find themes that span MULTIPLE episodes/shows. Do not invent claims.
- EVERY claim must be supported by `evidence`, and each evidence string must
  name the source show it came from (e.g. "Acquired: ...").
- `delta` describes how this theme relates to the PREVIOUS insights: "new",
  "reinforced", or "shifted" (and how). If there are no previous insights, say so.
- `implication` is written for this lens: {lens}

Return ONLY a JSON array (no prose, no code fences). Each element:
{{"title": str, "claim": str, "evidence": [str, ...], "implication": str,
  "delta": str, "sources": [str, ...]}}
"""


def _format_episodes(episodes: list[EpisodeSummary]) -> str:
    blocks = []
    for ep in episodes:
        points = "\n".join(f"    - {p}" for p in ep.key_points)
        blocks.append(f"- {ep.show} — \"{ep.title}\"\n{points or '    (no key points)'}")
    return "\n".join(blocks)


def _format_previous(previous: list[Insight]) -> str:
    if not previous:
        return "(none — this is the first digest)"
    return "\n".join(f"- {ins.claim}" for ins in previous)


def build_prompt(episodes: list[EpisodeSummary], previous: list[Insight], lens: str) -> str:
    return (
        _INSTRUCTIONS.format(lens=lens)
        + "\n\nPREVIOUS INSIGHTS:\n" + _format_previous(previous)
        + "\n\nEPISODES:\n" + _format_episodes(episodes)
    )


def parse_insights(raw: str) -> list[Insight]:
    """Parse a model reply (tolerant of code fences / surrounding text) to Insights."""
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    # Fall back to the first [...] block.
    if not text.startswith("["):
        bracket = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket:
            text = bracket.group(0)
    data = json.loads(text)
    insights: list[Insight] = []
    for item in data:
        insights.append(Insight(
            title=str(item.get("title", item.get("claim", "insight"))[:120]),
            claim=str(item.get("claim", "")),
            evidence=[str(e) for e in item.get("evidence", [])],
            implication=str(item.get("implication", "")),
            delta=str(item.get("delta", "")),
            sources=[str(s) for s in item.get("sources", [])],
        ))
    return insights


class LLMReasoner:
    """Reasoner backed by a user-supplied model `complete(prompt) -> text`."""

    def __init__(self, complete: Complete, lens: str = "founder/investor") -> None:
        self._complete = complete
        self.lens = lens

    def __call__(self, episodes: list[EpisodeSummary], previous: list[Insight]) -> list[Insight]:
        prompt = build_prompt(episodes, previous, self.lens)
        return parse_insights(self._complete(prompt))
