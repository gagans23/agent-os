# Easy install + the web UI 🖥️

> Module 3. The "click a button" goal: a non-technical person installs agent-os in
> one command and drives it from a browser. `install.sh` + `agent_os/webui.py`.

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/gagans23/agent-os/main/install.sh | bash
# or, from a clone:
./install.sh
```

`install.sh` is deliberately boring and safe:

- **No sudo, no global state.** It creates a local `.venv` in the project folder.
- **Checks Python 3.11+** before doing anything, with a clear error if missing.
- **Clones** the repo if you're not already inside it.
- Installs the **Ninja Harness eval gate** (from git until it's on PyPI) and
  **agent-os**, then runs a `/ping` smoke test.
- Prints exactly how to launch the UI and (optionally) plug in a free local model.

Override the interpreter with `PYTHON=/path/to/python3.11 ./install.sh`.

## The web UI

```bash
agent-os ui                       # http://127.0.0.1:8765, opens your browser
agent-os ui --port 9000 --no-browser
```

One page, served by Python's standard-library `http.server` — **nothing extra to
install**. It gives a non-technical user buttons for the common actions and three
focused cards:

- **🧠 Teach the brain** — paste notes or a file path → `/learn`.
- **❓ Ask your brain** — a question → `/ask`, answered only from your context and
  scored for grounding.
- **⚙️ Run a task** — `/run`; read-only tasks auto-run, write/send/deploy are gated.
- Quick actions: Status, Health, Agents, Skills, Model, Audit, Pending, Digest,
  Browser demo — plus a raw `/command` box.

### It's the same governed router

The UI is a thin transport. Every request hits `POST /api/cmd`, which calls the
**same `CommandRouter`** as the CLI and the WhatsApp surface. That means nothing is
bypassed:

- every command is **audited** (hash-chained, tamper-evident),
- **risk gating** still applies — write/send/deploy tasks queue for approval,
- answers are **scored by Ninja Harness**,
- the router's **error boundary** turns any failure into a friendly message.

```
Browser ──POST /api/cmd──> CommandRouter ──> risk gate ──> execute ──> Ninja score
                                  └────────────> audit log (every call)
```

## Security model

- **Localhost by default.** The server binds to `127.0.0.1`. It is **not**
  exposed to your network and has **no built-in authentication**.
- **Do not** put it on `0.0.0.0` or a public port without your own auth/TLS in
  front (e.g. a reverse proxy, or the Cloudflare Tunnel from `deploy/`).
- All the platform's controls (allowlist, risk default-deny, approvals, audit)
  still apply because the UI goes through the router. See [SECURITY.md](../SECURITY.md).

## Endpoints

| method | path | purpose |
|---|---|---|
| `GET` | `/` | the single-page UI |
| `POST` | `/api/cmd` | body `{"command": "/status"}` → `{"output": "..."}` |

That's the whole surface — small on purpose, stdlib-only, easy to audit.

## Programmatic use

```python
from agent_os.webui import serve
serve(host="127.0.0.1", port=8765)          # builds a router and blocks
# or bring your own (pre-wired with a provider, custom dirs, etc.):
from agent_os.command_router import CommandRouter
serve(router=CommandRouter(...), open_browser=False)
```
