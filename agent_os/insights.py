"""
insights — cross-episode (cross-source) synthesis with memory-based deltas.

Turns a set of per-episode summaries into structured "insights": each is a
claim/theme, the evidence behind it (every point cites its source episode), an
implication for a chosen lens (e.g. founder/investor), and a delta versus the
*previous* run — the part that makes the system compound over time.

Design:
- A strict schema (Insight / EpisodeSummary / Digest) so output is consistent
  and checkable by Ninja Harness (grounding = claims backed by evidence).
- A pluggable `reasoner(episodes, previous_insights) -> list[Insight]` — supply
  your LLM here. A deterministic keyword fallback ships so the loop runs and is
  testable without a model (it only surfaces real overlap; it never invents).
- Memory: the previous digest is loaded to compute "delta vs previous state".

No model and no feed/podcast API are bundled or faked. You provide the episode
summaries (from your RSS/YouTube fetcher) and, for rich prose, the reasoner.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

_STOP = {"the", "and", "for", "that", "this", "with", "from", "are", "was", "not",
         "you", "your", "but", "all", "can", "has", "have", "they", "their", "what",
         "when", "how", "why", "out", "about", "into", "than", "more", "less", "a",
         "an", "to", "of", "in", "on", "is", "it", "as", "by", "or", "be", "at"}


@dataclass
class EpisodeSummary:
    episode_id: str
    show: str
    title: str
    url: str = ""
    is_paid: bool = False
    published: str = ""
    summary: str = ""
    key_points: list[str] = field(default_factory=list)


@dataclass
class Insight:
    title: str
    claim: str
    evidence: list[str] = field(default_factory=list)   # each point cites its source
    implication: str = ""
    delta: str = ""                                     # vs previous run
    sources: list[str] = field(default_factory=list)    # episode ids/titles


@dataclass
class Digest:
    date: str
    lens: str
    episodes: list[EpisodeSummary] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        free = [e for e in self.episodes if not e.is_paid]
        lines = [f"Podcast digest — {self.date}", f"{len(free)} free episode(s):", ""]
        for i, e in enumerate(self.episodes, 1):
            tag = "paid" if e.is_paid else "free"
            lines.append(f"{i}. {e.show} — \"{e.title}\" — {tag}"
                         + (f"; published {e.published}" if e.published else ""))
        lines += ["", "Cross-episode insights", ""]
        for i, ins in enumerate(self.insights, 1):
            lines.append(f"{i}) {ins.title}")
            lines.append(f"- Claim/theme: {ins.claim}")
            if ins.evidence:
                lines.append("- Evidence: " + "; ".join(ins.evidence[:4]))
            if ins.implication:
                lines.append(f"- Implication ({self.lens}): {ins.implication}")
            if ins.delta:
                lines.append(f"- Delta vs previous: {ins.delta}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def as_trace_inputs(self) -> tuple[str, list[str]]:
        """Return (final_output, references) for Ninja Harness grounding: the
        rendered digest as the answer, and the episode evidence as references."""
        refs: list[str] = []
        for e in self.episodes:
            refs.extend(e.key_points)
            if e.summary:
                refs.append(e.summary)
        return self.render(), refs


# reasoner(episodes, previous_insights) -> list[Insight]
Reasoner = Callable[[list[EpisodeSummary], list[Insight]], list[Insight]]


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def keyword_reasoner(episodes: list[EpisodeSummary],
                     previous: list[Insight]) -> list[Insight]:
    """Deterministic fallback: surface themes that appear across >= 2 episodes.

    Honest by construction — it only restates overlapping key points and cites
    the episodes they came from; it does not invent claims or quotes. Swap in an
    LLM reasoner for the rich prose synthesis.
    """
    # token -> list of (episode, point)
    hits: dict[str, list[tuple[EpisodeSummary, str]]] = {}
    for ep in episodes:
        for point in ep.key_points:
            for tok in _tokens(point):
                hits.setdefault(tok, []).append((ep, point))

    prev_terms = {t for ins in previous for t in _tokens(ins.claim)}
    # Themes shared by at least two distinct shows.
    shared = []
    for tok, occ in hits.items():
        shows = {ep.show for ep, _ in occ}
        if len(shows) >= 2:
            shared.append((tok, len(occ), occ))
    shared.sort(key=lambda x: (-x[1], x[0]))

    insights: list[Insight] = []
    for tok, _count, occ in shared[:5]:
        shows = sorted({ep.show for ep, _ in occ})
        evidence = [f"{ep.show}: {point}" for ep, point in occ[:4]]
        sources = sorted({ep.title for ep, _ in occ})
        delta = "New theme vs previous digest." if tok not in prev_terms \
            else "Reinforced — also present in the previous digest."
        insights.append(Insight(
            title=f"Shared theme: '{tok}'",
            claim=f"{' and '.join(shows)} both touch on '{tok}'.",
            evidence=evidence,
            implication="(supply an LLM reasoner for a tailored implication)",
            delta=delta,
            sources=sources,
        ))
    if not insights:
        insights.append(Insight(
            title="No strong cross-episode overlap",
            claim="Today's episodes did not share an obvious common theme.",
            delta="(deterministic fallback found no shared keywords)",
        ))
    return insights


class CrossEpisodeSynthesizer:
    """Produce a Digest from episode summaries, with a delta vs the previous run."""

    def __init__(self, reasoner: Reasoner | None = None, memory=None) -> None:
        self.reasoner = reasoner or keyword_reasoner
        self.memory = memory  # optional AgentMemory for delta-vs-previous

    def _load_previous(self) -> list[Insight]:
        if self.memory is None:
            return []
        raw = self.memory.recall("digest:latest")
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return [Insight(**i) for i in data.get("insights", [])]
        except Exception:  # noqa: BLE001
            return []

    def synthesize(self, episodes: list[EpisodeSummary],
                   lens: str = "founder/investor", date: str | None = None) -> Digest:
        date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        previous = self._load_previous()
        insights = self.reasoner(episodes, previous)
        digest = Digest(date=date, lens=lens, episodes=episodes, insights=insights)
        if self.memory is not None:
            payload = json.dumps(digest.to_dict(), default=str)
            self.memory.remember("digest:latest", payload, category="digest")
            self.memory.remember(f"digest:{date}", payload, category="digest")
        return digest


def trending_terms(episodes: list[EpisodeSummary], top: int = 8) -> list[tuple[str, int]]:
    """Most frequent meaningful terms across episode key points (utility/demo)."""
    c: Counter[str] = Counter()
    for ep in episodes:
        for point in ep.key_points:
            c.update(_tokens(point))
    return c.most_common(top)
