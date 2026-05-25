"""
providers — plug your own model into agent-os.

One small adapter powers three roles across the platform:

  - reasoner : text completion (the `/ask` answer, the `/digest` prose)
  - embedder : vectors for semantic retrieval in the Brain (`context.py`)
  - agent_fn : the worker behind `/run` and `/ask`

Principles (non-negotiable, same as the rest of agent-os):

  - **Ollama-first.** The default is a local, free model so a non-technical user
    can run everything with **no API key and no cloud account**.
  - **Never bundled, never faked.** API keys are read from the environment at call
    time; nothing is hardcoded and no network call happens unless YOU configure a
    provider. With no provider configured, agent-os stays in deterministic mode.
  - **Dependency-light.** HTTP uses the Python standard library (`urllib`) — no
    `openai`/`anthropic`/`requests` SDK required to install agent-os.

Configure with one environment variable::

    export AGENT_OS_PROVIDER="ollama:llama3"            # local + free (default host)
    export AGENT_OS_PROVIDER="openai:gpt-4o-mini"       # needs OPENAI_API_KEY
    export AGENT_OS_PROVIDER="anthropic:claude-3-5-sonnet-20241022"  # ANTHROPIC_API_KEY
    export AGENT_OS_PROVIDER="echo"                     # offline, deterministic (tests)

Any OpenAI-compatible endpoint (Together, vLLM, LM Studio, Replit's proxy, …)
works via the openai provider with a custom base URL::

    export AGENT_OS_PROVIDER="openai:llama-3.1-70b"
    export OPENAI_BASE_URL="https://your-endpoint/v1"
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable

Complete = Callable[[str], str]
Embedder = Callable[[list[str]], list[list[float]]]


class ProviderError(RuntimeError):
    """Raised when a provider is misconfigured or a model call fails."""


def _http_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 60.0) -> dict:
    """POST JSON and parse JSON back, using only the standard library.

    Network/HTTP errors are surfaced as ProviderError with a readable message —
    never a raw traceback to the user (the router's error boundary also catches)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-configured URL
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        body = exc.read().decode("utf-8", "ignore")[:300]
        raise ProviderError(f"{url} returned HTTP {exc.code}: {body}") from None
    except urllib.error.URLError as exc:  # pragma: no cover - network dependent
        raise ProviderError(
            f"could not reach {url} ({exc.reason}). "
            "Is the model server running? For Ollama: `ollama serve`."
        ) from None


def _require_env(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        raise ProviderError(
            f"environment variable {var} is not set. agent-os never bundles keys — "
            f"export {var} with your own credential to use this provider."
        )
    return val


class Provider(ABC):
    """A model backend exposing the two primitives agent-os needs."""

    name: str = "provider"

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return a text completion for `prompt`."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    # convenience adapters into the callables the rest of agent-os expects -----

    def as_reasoner(self) -> Complete:
        return lambda prompt: self.complete(prompt)

    def as_embedder(self) -> Embedder:
        return self.embed

    def as_agent_fn(self) -> Callable[[str, str, object], str]:
        """An agent_fn(command, context, job) for the command router/runner."""
        def _agent(command: str, context: str, job: object) -> str:
            try:
                job.add_step("action", f"Calling {self.name} for a completion.")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - job may be a stub in tests
                pass
            return self.complete(command)
        return _agent


class OllamaProvider(Provider):
    """Local, free model via Ollama (https://ollama.com). The recommended default."""

    def __init__(self, model: str = "llama3", host: str | None = None,
                 embed_model: str | None = None, timeout: float = 120.0) -> None:
        self.model = model
        self.embed_model = embed_model or model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.timeout = timeout
        self.name = f"ollama:{model}"

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        resp = _http_json(f"{self.host}/api/generate", payload, {}, self.timeout)
        return str(resp.get("response", "")).strip()

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            resp = _http_json(f"{self.host}/api/embeddings",
                              {"model": self.embed_model, "prompt": text}, {}, self.timeout)
            out.append([float(x) for x in resp.get("embedding", [])])
        return out


class OpenAIProvider(Provider):
    """OpenAI, or ANY OpenAI-compatible endpoint via OPENAI_BASE_URL."""

    def __init__(self, model: str = "gpt-4o-mini", api_key_env: str = "OPENAI_API_KEY",
                 base_url: str | None = None, embed_model: str = "text-embedding-3-small",
                 timeout: float = 60.0) -> None:
        self.model = model
        self.embed_model = embed_model
        self.api_key_env = api_key_env
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self.name = f"openai:{model}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {_require_env(self.api_key_env)}"}

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = _http_json(f"{self.base_url}/chat/completions",
                          {"model": self.model, "messages": messages},
                          self._headers(), self.timeout)
        return str(resp["choices"][0]["message"]["content"]).strip()

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = _http_json(f"{self.base_url}/embeddings",
                          {"model": self.embed_model, "input": texts},
                          self._headers(), self.timeout)
        return [[float(x) for x in d["embedding"]] for d in resp["data"]]


class AnthropicProvider(Provider):
    """Anthropic Claude via the Messages API."""

    def __init__(self, model: str = "claude-3-5-sonnet-20241022",
                 api_key_env: str = "ANTHROPIC_API_KEY", max_tokens: int = 1024,
                 timeout: float = 60.0) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.name = f"anthropic:{model}"

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict = {"model": self.model, "max_tokens": self.max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}
        if system:
            payload["system"] = system
        headers = {"x-api-key": _require_env(self.api_key_env),
                   "anthropic-version": "2023-06-01"}
        resp = _http_json("https://api.anthropic.com/v1/messages", payload, headers, self.timeout)
        parts = resp.get("content", [])
        return "".join(p.get("text", "") for p in parts).strip()

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise ProviderError(
            "Anthropic does not offer an embeddings API. For the Brain's semantic "
            "search, set an embedding provider (e.g. ollama:nomic-embed-text or "
            "openai:text-embedding-3-small) — the reasoner and embedder can differ."
        )


class EchoProvider(Provider):
    """Offline, deterministic provider — no network, no key.

    It is honest about what it is: `complete()` echoes a labeled summary of the
    prompt, and `embed()` returns a deterministic hashed bag-of-words vector
    (NOT semantic — a stand-in so the embedder code path is testable without a
    model). Use it for tests and for running the loop fully offline."""

    DIM = 256

    def __init__(self) -> None:
        self.name = "echo"

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        head = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return f"[echo] {head[:200]}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.DIM
            for tok in text.lower().split():
                h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest(), 16)
                vec[h % self.DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


_BUILDERS: dict[str, Callable[[str], Provider]] = {
    "ollama": lambda model: OllamaProvider(model or "llama3"),
    "openai": lambda model: OpenAIProvider(model or "gpt-4o-mini"),
    "anthropic": lambda model: AnthropicProvider(model or "claude-3-5-sonnet-20241022"),
    "echo": lambda _model: EchoProvider(),
}


def get_provider(spec: str) -> Provider:
    """Build a provider from a ``"kind:model"`` spec (e.g. ``"ollama:llama3"``).

    The model part is optional (``"openai"`` → a sensible default model)."""
    spec = (spec or "").strip()
    if not spec:
        raise ProviderError("empty provider spec. Try 'ollama:llama3' or 'echo'.")
    kind, _, model = spec.partition(":")
    builder = _BUILDERS.get(kind.lower())
    if builder is None:
        known = ", ".join(sorted(_BUILDERS))
        raise ProviderError(f"unknown provider '{kind}'. Known: {known}.")
    return builder(model.strip())


def provider_from_env(var: str = "AGENT_OS_PROVIDER") -> Provider | None:
    """Return the configured provider, or None if the env var is unset.

    This is the opt-in switch: with no provider configured, callers stay in
    deterministic mode and agent-os makes no model calls."""
    spec = os.environ.get(var)
    return get_provider(spec) if spec else None
