#!/usr/bin/env python3
"""
Multi-day delta demo — shows how insights COMPOUND across runs via memory.

Day 1 introduces themes (all "new"). Day 2 repeats some + adds others → the
repeated ones come back as "reinforced", the fresh ones as "new". This is the
delta-vs-previous mechanism that turns a daily digest into a trend.

    python examples/multiday_digest_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_os.agent_memory import AgentMemory
from agent_os.insights import CrossEpisodeSynthesizer, EpisodeSummary

DAY1 = [
    EpisodeSummary("a1", "Acquired", "Vanguard", key_points=[
        "Durable outcomes came from redesigning incentives, not heroics.",
        "Customer ownership aligns incentives with investors."]),
    EpisodeSummary("b1", "Huberman Lab", "Social Anxiety", key_points=[
        "Durable change comes from updating incentives and feedback.",
        "Real exposure beats simulated practice."]),
]

DAY2 = [
    EpisodeSummary("a2", "Acquired", "Costco", key_points=[
        "Membership incentives align the company with the customer.",
        "Pricing discipline is the durable moat."]),
    EpisodeSummary("b2", "Dwarkesh", "Scaling", key_points=[
        "Pricing of compute shapes which research is durable.",
        "Feedback loops compound advantages over time."]),
]


def _deltas(digest) -> list[str]:
    return [f"'{i.title.split(chr(39))[1] if chr(39) in i.title else i.title}': {i.delta}"
            for i in digest.insights]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        mem = AgentMemory(Path(tmp) / "state")
        synth = CrossEpisodeSynthesizer(memory=mem)

        print("=== Day 1 ===")
        d1 = synth.synthesize(DAY1, date="2026-05-18")
        for line in _deltas(d1):
            print("  " + line)

        print("\n=== Day 2 (note 'incentives'/'durable' return as reinforced) ===")
        d2 = synth.synthesize(DAY2, date="2026-05-19")
        for line in _deltas(d2):
            print("  " + line)

        reinforced = [i for i in d2.insights if "Reinforced" in i.delta]
        new = [i for i in d2.insights if "New theme" in i.delta]
        print(f"\nDay 2 summary: {len(reinforced)} reinforced, {len(new)} new theme(s).")
        mem.close()


if __name__ == "__main__":
    main()
