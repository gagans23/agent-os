#!/usr/bin/env python3
"""
Cross-episode insights demo (mirrors the two-episode digest pattern).

Shows the whole loop with the deterministic fallback reasoner — no model, no
feed API. Plug in your own `reasoner=` (LLM) for the rich prose, and your feed
fetcher to build the EpisodeSummary list.

    python examples/podcast_digest_demo.py
"""

from __future__ import annotations

from agent_os.agent_memory import AgentMemory
from agent_os.insights import CrossEpisodeSynthesizer, EpisodeSummary

EPISODES = [
    EpisodeSummary(
        episode_id="acquired-vanguard",
        show="Acquired",
        title="Vanguard: the communist capitalist who saved investors a trillion dollars",
        url="", is_paid=False, published="2026-05-18",
        summary="How Vanguard's customer-owned structure made low fees structural.",
        key_points=[
            "Vanguard is owned by its fund customers, aligning incentives with investors.",
            "Bogle's insight: fees are a drag; minimizing fees is the cleanest way to improve returns.",
            "Durable outcomes came from redesigning incentives, not heroics.",
        ],
    ),
    EpisodeSummary(
        episode_id="huberman-epley",
        show="Huberman Lab",
        title="How to Overcome Social Anxiety | Dr. Nick Epley",
        url="", is_paid=False, published="2026-05-18",
        summary="Real-world feedback updates false beliefs about other people.",
        key_points=[
            "Social anxiety improves with real exposure, not just simulated practice.",
            "Asking people for help reveals acceptance is more common than feared.",
            "Durable change comes from updating incentives and feedback, not willpower.",
        ],
    ),
]


def main() -> None:
    memory = AgentMemory("agent_state")
    synth = CrossEpisodeSynthesizer(memory=memory)  # default = keyword fallback
    digest = synth.synthesize(EPISODES, lens="founder/investor")
    print(digest.render())

    # Optional: score the digest with Ninja Harness (grounding + output hygiene).
    try:
        from ninja_harness.adapters import detect_adapter
        from ninja_harness.schemas import EvaluationCase
        from ninja_harness.scoring.ninja_score import NinjaScoreAggregator

        final, refs = digest.as_trace_inputs()
        trace = {"agent_name": "PodcastDigest", "task": "cross-episode digest",
                 "final_output": final}
        run = detect_adapter(trace).parse(trace)
        case = EvaluationCase(task="cross-episode digest", references=refs)
        result = NinjaScoreAggregator().evaluate(run, case)
        g = result.metric_by_name("grounding")
        h = result.metric_by_name("output_hygiene")
        print(f"\n[Ninja Harness] grounding={g.score:.2f}  hygiene={h.score:.2f}  "
              f"cert={result.certification}")
    except ImportError:
        print("\n(install ninja-harness to score the digest)")

    memory.close()


if __name__ == "__main__":
    main()
