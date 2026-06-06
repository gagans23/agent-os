"""Tests for the gated skill-proposal logic (the closed learning loop)."""

from __future__ import annotations

from agent_os.skill_synth import (
    SkillDraft,
    propose_skill,
    slugify,
    trace_complexity,
)

_GOOD_TRACE = {
    "job_id": "job-xyz",
    "steps": [
        {"step_type": "plan", "output": "List the top local LLM runtimes."},
        {"step_type": "action", "output": "Compare license, RAM, speed."},
        {"step_type": "observation", "output": "Built a comparison table."},
    ],
    "tool_calls": [{"tool_name": "browser_open"}],
}


def test_slugify_drops_stopwords_and_limits() -> None:
    assert slugify("run summarize the quarterly budget for me") == "summarize-quarterly-budget"
    assert slugify("???") == "task"  # no usable tokens → safe default


def test_trace_complexity_counts_steps_and_tools() -> None:
    assert trace_complexity(_GOOD_TRACE) == 4
    assert trace_complexity({}) == 0


def test_propose_skill_happy_path() -> None:
    draft = propose_skill(
        "research the top local LLM runtimes and compare them",
        score=92.0, certification="PASS", matched_skill=None,
        trace=_GOOD_TRACE, existing_names=set(),
    )
    assert isinstance(draft, SkillDraft)
    assert draft.name == "research-top-local-llm-runtimes"  # slug (5 non-stopword tokens)
    assert "llm" in draft.triggers or "runtimes" in draft.triggers
    assert "comparison table" in draft.procedure  # rebuilt from the trace steps
    md = draft.to_markdown()
    assert md.startswith("---") and "## Procedure" in md
    assert "name: research-top-local-llm-runtimes" in md
    assert draft.source_job_id == "job-xyz"


def test_propose_skill_skips_when_a_skill_already_matched() -> None:
    assert propose_skill("x y z task here", score=99.0, certification="PASS",
                         matched_skill=object(), trace=_GOOD_TRACE,
                         existing_names=set()) is None


def test_propose_skill_skips_low_score() -> None:
    assert propose_skill("research runtimes compare them now", score=50.0,
                         certification="FAIL", matched_skill=None,
                         trace=_GOOD_TRACE, existing_names=set()) is None


def test_propose_skill_skips_trivial_runs() -> None:
    thin = {"steps": [{"step_type": "action", "output": "did one thing"}], "tool_calls": []}
    assert propose_skill("do a quick thing here please", score=95.0, certification="PASS",
                         matched_skill=None, trace=thin, existing_names=set()) is None


def test_propose_skill_skips_when_name_exists() -> None:
    draft = propose_skill("research the top local LLM runtimes and compare",
                          score=92.0, certification="PASS", matched_skill=None,
                          trace=_GOOD_TRACE, existing_names=set())
    assert draft is not None
    again = propose_skill("research the top local LLM runtimes and compare",
                          score=92.0, certification="PASS", matched_skill=None,
                          trace=_GOOD_TRACE, existing_names={draft.name})
    assert again is None
