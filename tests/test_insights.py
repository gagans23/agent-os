"""Tests for cross-episode insight synthesis."""

from __future__ import annotations

from agent_os.agent_memory import AgentMemory
from agent_os.insights import (
    CrossEpisodeSynthesizer,
    EpisodeSummary,
    Insight,
    keyword_reasoner,
    trending_terms,
)


def _episodes() -> list[EpisodeSummary]:
    return [
        EpisodeSummary("a", "Acquired", "Vanguard", key_points=[
            "Durable outcomes came from redesigning incentives, not heroics.",
            "Customer ownership aligns incentives with investors.",
        ]),
        EpisodeSummary("b", "Huberman Lab", "Social Anxiety", key_points=[
            "Durable change comes from updating incentives and feedback.",
            "Real exposure beats simulated practice.",
        ]),
    ]


def test_keyword_reasoner_finds_shared_theme() -> None:
    insights = keyword_reasoner(_episodes(), previous=[])
    # 'incentives' appears in both shows → a shared-theme insight
    assert any("incentive" in ins.claim.lower() for ins in insights)
    top = insights[0]
    assert top.evidence  # cites episode points
    assert top.sources
    assert "New theme" in top.delta  # no previous digest


def test_no_overlap_yields_placeholder() -> None:
    eps = [
        EpisodeSummary("a", "Show A", "T", key_points=["bananas are yellow"]),
        EpisodeSummary("b", "Show B", "T", key_points=["rockets reach orbit"]),
    ]
    insights = keyword_reasoner(eps, previous=[])
    assert insights and "No strong cross-episode overlap" in insights[0].title


def test_synthesize_renders_digest() -> None:
    digest = CrossEpisodeSynthesizer().synthesize(_episodes(), lens="founder/investor")
    text = digest.render()
    assert "Cross-episode insights" in text
    assert "Claim/theme:" in text
    assert "Delta vs previous:" in text


def test_delta_uses_memory(tmp_path) -> None:
    mem = AgentMemory(tmp_path / "state")
    synth = CrossEpisodeSynthesizer(memory=mem)
    # First run → "New theme"
    d1 = synth.synthesize(_episodes())
    assert any("New theme" in i.delta for i in d1.insights)
    # Second run with the same themes → "Reinforced" (loaded from memory)
    d2 = synth.synthesize(_episodes())
    assert any("Reinforced" in i.delta for i in d2.insights)
    mem.close()


def test_as_trace_inputs_for_grounding() -> None:
    digest = CrossEpisodeSynthesizer().synthesize(_episodes())
    final, refs = digest.as_trace_inputs()
    assert "Cross-episode insights" in final
    assert len(refs) >= 4  # episode key points become grounding references


def test_pluggable_reasoner() -> None:
    def my_reasoner(episodes, previous):
        return [Insight(title="custom", claim="my claim", evidence=["e"], implication="impl")]

    digest = CrossEpisodeSynthesizer(reasoner=my_reasoner).synthesize(_episodes())
    assert digest.insights[0].title == "custom"


def test_trending_terms() -> None:
    terms = dict(trending_terms(_episodes()))
    assert "incentives" in terms
