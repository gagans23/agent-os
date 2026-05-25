# Model onboarding 🧩 — plug in your model

> Module 2. `agent_os/providers.py`. Bring your own model with one environment
> variable. Ollama-first, so a non-technical user runs everything locally and free.

agent-os ships **no model and no API keys**. You plug one in, and it powers three
roles across the platform at once:

| role | callable | used by |
|---|---|---|
| **reasoner** | `complete(prompt) -> str` | `/ask` answers, `/digest` synthesis |
| **embedder** | `embed(texts) -> vectors` | the Brain's semantic / hybrid search |
| **agent_fn** | `agent_fn(command, context, job) -> str` | the worker behind `/run` |

## Quick start

```bash
export AGENT_OS_PROVIDER="ollama:llama3"                        # local + free, no key
export AGENT_OS_PROVIDER="openai:gpt-4o-mini"                   # needs OPENAI_API_KEY
export AGENT_OS_PROVIDER="anthropic:claude-3-5-sonnet-20241022" # needs ANTHROPIC_API_KEY
agent-os cmd "/model"                                          # show what's wired
```

```python
from agent_os.providers import get_provider, provider_from_env
p = get_provider("ollama:llama3")          # explicit
p = provider_from_env()                     # or read AGENT_OS_PROVIDER (None if unset)
p.complete("Explain adding fractions to a 10-year-old.")
p.embed(["add fractions", "multiply fractions"])
```

See `examples/provider_demo.py` for a runnable, offline walkthrough.

## Principles (non-negotiable)

- **Ollama-first.** The default provider is a local, free model so anyone can run
  the whole system with **no key and no cloud account**.
- **Never bundled, never faked.** API keys are read from the environment **at call
  time**; nothing is hardcoded. With **no provider configured, agent-os stays in
  deterministic mode and makes zero model calls** — every external call is opt-in
  and uses *your* credentials.
- **Dependency-light.** HTTP uses the Python standard library (`urllib`). agent-os
  installs with **no `openai` / `anthropic` / `requests` SDK**.

## Providers

| provider | spec | key | embeddings | notes |
|---|---|---|---|---|
| **Ollama** | `ollama:<model>` | none | yes | local + free; `OLLAMA_HOST` to override; the recommended default |
| **OpenAI** | `openai:<model>` | `OPENAI_API_KEY` | yes | any OpenAI-compatible endpoint via `OPENAI_BASE_URL` |
| **Anthropic** | `anthropic:<model>` | `ANTHROPIC_API_KEY` | — | Claude Messages API; no embeddings API (pair with an embed provider) |
| **Echo** | `echo` | none | yes* | offline & deterministic; for tests and no-model runs |

\* Echo's `embed()` is a deterministic hashed bag-of-words vector — **not
semantic**. It's an honest stand-in so the embedder code path is testable
offline; it does not pretend to be a model.

### Any OpenAI-compatible endpoint

Together, vLLM, LM Studio, a local proxy, Replit's model proxy — anything that
speaks the OpenAI Chat Completions / Embeddings API:

```bash
export AGENT_OS_PROVIDER="openai:llama-3.1-70b"
export OPENAI_BASE_URL="https://your-endpoint/v1"
export OPENAI_API_KEY="..."
```

### Mixing reasoner and embedder

The reasoner and embedder can be different models. Claude has no embeddings API,
so for the Brain's semantic search pair it with an embedding provider:

```python
ContextStore(embedder=get_provider("ollama:nomic-embed-text").as_embedder())
```

## How it wires into the runtime

The `CommandRouter` is **opt-in**: pass `provider=` or set `AGENT_OS_PROVIDER`.

```python
from agent_os.command_router import CommandRouter
from agent_os.providers import get_provider
router = CommandRouter(provider=get_provider("ollama:llama3"))
```

When a provider is present the router:

1. uses it as the **agent_fn** for `/ask` and `/run` (real answers),
2. uses it as the **reasoner** for `/digest` (cross-episode synthesis),
3. attaches its **embedder** to the Brain and reindexes existing chunks.

With no provider, all three stay deterministic. Errors (bad spec, unreachable
server, missing key) surface as a readable `ProviderError`, caught by the router's
error boundary — never a raw stack trace to the user.

## API

```python
class Provider:
    name: str
    def complete(self, prompt: str, *, system: str | None = None) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def as_reasoner(self) -> Callable[[str], str]: ...
    def as_embedder(self) -> Callable[[list[str]], list[list[float]]]: ...
    def as_agent_fn(self) -> Callable[[str, str, object], str]: ...

get_provider(spec: str) -> Provider              # "ollama:llama3", raises on unknown
provider_from_env(var="AGENT_OS_PROVIDER") -> Provider | None   # opt-in switch
```
