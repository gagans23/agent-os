#!/usr/bin/env python3
"""
Ahaan's maths brain — the keystone example.

A child uploads his maths notes; agent-os ingests them into a personal knowledge
base (the Brain), then answers his questions **grounded only in his own notes**,
and **scores** each answer with Ninja Harness so weak/ungrounded answers are
flagged. No external services, no API key required.

    python examples/ahaan_maths_demo.py

Plug in a real model to get natural-language answers (Ollama is local + free):

    export AGENT_OS_PROVIDER=ollama:llama3
    python examples/ahaan_maths_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_os.command_router import CommandRouter

AHAAN_NOTES = """Adding fractions

To add fractions with the same denominator, add the numerators and keep the
denominator the same. For example 1/4 + 2/4 = 3/4.

Multiplying fractions

To multiply two fractions, multiply the numerators together and multiply the
denominators together. For example 2/3 * 3/4 = 6/12 = 1/2.

Equivalent fractions

Two fractions are equivalent if they represent the same value. Multiply or divide
the numerator and denominator by the same number. For example 1/2 = 2/4 = 3/6.
"""


def main() -> None:
    # A throwaway workspace so the demo is repeatable and never pollutes the repo.
    with tempfile.TemporaryDirectory() as tmp:
        notes = Path(tmp) / "ahaan_maths_notes.md"
        notes.write_text(AHAAN_NOTES)

        from agent_os.agent_memory import AgentMemory
        from agent_os.jobs import JobStore
        from agent_os.trace_recorder import TraceRecorder

        router = CommandRouter(
            jobs=JobStore(Path(tmp) / "jobs.db"),
            memory=AgentMemory(Path(tmp) / "state"),
            recorder=TraceRecorder(Path(tmp) / "traces"),
        )
        try:
            print("=" * 70)
            print("Ahaan's maths brain  ·  agent-os")
            print("=" * 70)
            print(router.handle("/model").splitlines()[0])  # which model (if any)
            print()

            # 1) Teach the brain: ingest the notes file.
            print(">>> /learn ahaan_maths_notes.md")
            print(router.handle(f"/learn {notes}"))
            print()

            # 2) Ask questions — answered ONLY from his notes, then scored.
            for question in (
                "how do I add fractions with the same denominator?",
                "how do I multiply fractions?",
                "what makes two fractions equivalent?",
            ):
                print(f">>> /ask {question}")
                print(router.handle(f"/ask {question}"))
                print()
        finally:
            router.close()

    print("Every answer is grounded in Ahaan's own notes and scored by Ninja "
          "Harness — ungrounded answers get flagged, so the brain stays honest.")


if __name__ == "__main__":
    main()
