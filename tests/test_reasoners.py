"""Tests for the LLM reasoner adapter (no real model — injected `complete`)."""

from __future__ import annotations

import json

import pytest

from agent_os.insights import EpisodeSummary, Insight
from agent_os.reasoners import LLMReasoner, build_prompt, parse_insights


def _episodes():
    return [
        EpisodeSummary("a", "Acquired", "Vanguard", key_points=["incentives matter"]),
        EpisodeSummary("b", "Huberman", "Anxiety", key_points=["feedback updates beliefs"]),
    ]


def test_build_prompt_includes_schema_and_episodes() -> None:
    p = build_prompt(_episodes(), [], "founder/investor")
    assert "JSON array" in p
    assert "Acquired" in p and "Huberman" in p
    assert "founder/investor" in p
    assert "first digest" in p  # no previous insights


def test_build_prompt_includes_previous() -> None:
    prev = [Insight(title="t", claim="prior claim about incentives")]
    p = build_prompt(_episodes(), prev, "lens")
    assert "prior claim about incentives" in p


def test_parse_plain_json() -> None:
    raw = json.dumps([{"title": "T", "claim": "C", "evidence": ["Acquired: x"],
                       "implication": "I", "delta": "new", "sources": ["Vanguard"]}])
    out = parse_insights(raw)
    assert len(out) == 1 and out[0].claim == "C"
    assert out[0].evidence == ["Acquired: x"]


def test_parse_tolerates_code_fences_and_prose() -> None:
    raw = "Here you go:\n```json\n[{\"claim\": \"C\", \"evidence\": []}]\n```\nThanks!"
    out = parse_insights(raw)
    assert out[0].claim == "C"


def test_llm_reasoner_uses_injected_complete() -> None:
    seen = {}

    def fake_complete(prompt: str) -> str:
        seen["prompt"] = prompt
        return json.dumps([{"title": "Shared", "claim": "both discuss incentives",
                            "evidence": ["Acquired: incentives matter"],
                            "implication": "underwrite incentives", "delta": "new"}])

    reasoner = LLMReasoner(fake_complete, lens="founder/investor")
    insights = reasoner(_episodes(), [])
    assert seen["prompt"]                       # the model was called with a prompt
    assert insights[0].claim == "both discuss incentives"
    assert insights[0].implication == "underwrite incentives"


def test_llm_reasoner_plugs_into_synthesizer() -> None:
    from agent_os.insights import CrossEpisodeSynthesizer

    def fake_complete(prompt: str) -> str:
        return '[{"claim": "themed", "evidence": ["Acquired: x"], "delta": "new"}]'

    synth = CrossEpisodeSynthesizer(reasoner=LLMReasoner(fake_complete))
    digest = synth.synthesize(_episodes())
    assert digest.insights[0].claim == "themed"


def test_parse_bad_json_raises() -> None:
    with pytest.raises(Exception):
        parse_insights("not json at all")
