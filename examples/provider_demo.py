#!/usr/bin/env python3
"""
Model onboarding — plug in your own model (Module 2).

agent-os ships no model and no keys. You bring one with a single environment
variable, and it powers three roles at once: the reasoner (completions), the
embedder (semantic search in the Brain), and the agent_fn behind /run.

This demo runs fully offline with the deterministic EchoProvider, then shows the
one line you'd change for a real, local, free model via Ollama.

    python examples/provider_demo.py

Real models (pick one; Ollama needs no key and runs locally):

    export AGENT_OS_PROVIDER=ollama:llama3
    export AGENT_OS_PROVIDER=openai:gpt-4o-mini            # OPENAI_API_KEY
    export AGENT_OS_PROVIDER=anthropic:claude-3-5-sonnet-20241022  # ANTHROPIC_API_KEY
"""

from __future__ import annotations

from agent_os.providers import EchoProvider, get_provider, provider_from_env


def main() -> None:
    # In production, read the configured provider from the environment.
    # Falls back to the offline EchoProvider so this demo always runs.
    provider = provider_from_env() or EchoProvider()
    print(f"Provider: {provider.name}")
    print("(set AGENT_OS_PROVIDER to switch — e.g. ollama:llama3 for local + free)\n")

    # Role 1 — reasoner: a text completion.
    answer = provider.complete("Explain adding fractions to a 10-year-old in one line.")
    print("complete() ->", answer)

    # Role 2 — embedder: vectors used by the Brain's semantic search.
    vectors = provider.embed(["add fractions", "multiply fractions"])
    print(f"embed()    -> {len(vectors)} vectors, dim {len(vectors[0])}")

    # The same adapters the router/runner consume.
    reasoner = provider.as_reasoner()        # Callable[[str], str]   (e.g. /digest)
    embedder = provider.as_embedder()        # Callable[[list[str]], list[list[float]]]
    print("as_reasoner() ->", reasoner("ping")[:60])
    print("as_embedder() ->", f"{len(embedder(['x']))} vector(s)")

    # You can also build a provider explicitly without touching the environment.
    explicit = get_provider("ollama:llama3")
    print(f"\nget_provider('ollama:llama3') -> {explicit.name} "
          f"(host {explicit.host}); run `ollama serve` to use it.")


if __name__ == "__main__":
    main()
