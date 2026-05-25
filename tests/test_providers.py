"""Tests for the model provider layer (Ollama/OpenAI/Anthropic/Echo).

Network is never touched: HTTP-backed providers are exercised by monkeypatching
the module's `_http_json`, and EchoProvider is fully offline.
"""

from __future__ import annotations

import pytest

from agent_os import providers
from agent_os.providers import (
    AnthropicProvider,
    EchoProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    get_provider,
    provider_from_env,
)

# --- factory ----------------------------------------------------------------

def test_get_provider_specs() -> None:
    assert get_provider("ollama:llama3").name == "ollama:llama3"
    assert get_provider("ollama").name == "ollama:llama3"          # default model
    assert get_provider("openai:gpt-4o-mini").name == "openai:gpt-4o-mini"
    assert get_provider("anthropic").name.startswith("anthropic:")
    assert isinstance(get_provider("echo"), EchoProvider)


def test_get_provider_rejects_unknown_and_empty() -> None:
    with pytest.raises(ProviderError):
        get_provider("nope:x")
    with pytest.raises(ProviderError):
        get_provider("")


def test_provider_from_env(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_OS_PROVIDER", raising=False)
    assert provider_from_env() is None                  # opt-in: unset → no provider
    monkeypatch.setenv("AGENT_OS_PROVIDER", "echo")
    assert isinstance(provider_from_env(), EchoProvider)


# --- echo (offline, deterministic) ------------------------------------------

def test_echo_complete_and_embed() -> None:
    p = EchoProvider()
    assert p.complete("hello world").startswith("[echo]")
    v1 = p.embed(["add fractions"])[0]
    v2 = p.embed(["add fractions"])[0]
    assert v1 == v2                                     # deterministic
    assert len(v1) == EchoProvider.DIM
    # different text → different vector
    assert p.embed(["photosynthesis"])[0] != v1


def test_adapters_match_expected_signatures() -> None:
    p = EchoProvider()
    assert p.as_reasoner()("q").startswith("[echo]")
    assert len(p.as_embedder()(["a", "b"])) == 2


def test_as_agent_fn_folds_context_into_prompt() -> None:
    # A matched skill's instructions reach the model (not hardwired to any vendor).
    from agent_os.providers import Provider

    captured: dict = {}

    class Capture(Provider):
        name = "capture"

        def complete(self, prompt, *, system=None):
            captured["prompt"] = prompt
            return "ok"

        def embed(self, texts):
            return [[0.0] for _ in texts]

    class _Job:
        def add_step(self, *a, **k):
            pass

    out = Capture().as_agent_fn()("research X", "## Matched skill: browser-research\nOpen pages", _Job())
    assert out == "ok"
    assert "research X" in captured["prompt"]
    assert "browser-research" in captured["prompt"]  # skill context was injected


# --- ollama (mocked transport) ----------------------------------------------

def test_ollama_complete_and_embed(monkeypatch) -> None:
    calls = {}

    def fake_http(url, payload, headers, timeout=60.0):
        calls["url"] = url
        if url.endswith("/api/generate"):
            return {"response": "  the answer  "}
        if url.endswith("/api/embeddings"):
            return {"embedding": [0.1, 0.2, 0.3]}
        raise AssertionError(url)

    monkeypatch.setattr(providers, "_http_json", fake_http)
    p = OllamaProvider(model="llama3")
    assert p.complete("q") == "the answer"              # stripped
    assert p.embed(["x"]) == [[0.1, 0.2, 0.3]]


# --- openai (mocked transport + key handling) -------------------------------

def test_openai_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        OpenAIProvider().complete("hi")


def test_openai_complete_mocked(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_http(url, payload, headers, timeout=60.0):
        assert headers["Authorization"] == "Bearer sk-test"
        return {"choices": [{"message": {"content": "hi there"}}]}

    monkeypatch.setattr(providers, "_http_json", fake_http)
    assert OpenAIProvider().complete("hi", system="be brief") == "hi there"


# --- anthropic --------------------------------------------------------------

def test_anthropic_complete_mocked(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

    def fake_http(url, payload, headers, timeout=60.0):
        assert "messages" in url
        assert headers["anthropic-version"]
        return {"content": [{"type": "text", "text": "claude says hi"}]}

    monkeypatch.setattr(providers, "_http_json", fake_http)
    assert AnthropicProvider().complete("hi") == "claude says hi"


def test_anthropic_embed_unsupported() -> None:
    with pytest.raises(ProviderError):
        AnthropicProvider().embed(["x"])
