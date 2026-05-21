# Deploying agent-os (Level 2 — Reliability)

These templates make the platform **stay alive and recover**. The code parts
(supervisor, health checks, retries, timeouts, token health, allowlist, daily
eval) ship in `agent_os/`. The pieces below need **your** accounts/machine — they
are configuration + service files you run, not bundled or faked integrations.

> Never commit real secrets. Tokens go in your environment / a secrets manager,
> not in these files.

## 1. Permanent Cloudflare named tunnel

A named tunnel gives your bridge a stable public hostname that survives reboots.
You run this with **your** Cloudflare account.

```bash
cloudflared tunnel login
cloudflared tunnel create agent-os
# copy the generated <TUNNEL_ID>.json credentials path into the config below
cloudflared tunnel route dns agent-os agent.example.com
cloudflared tunnel --config deploy/cloudflared-config.example.yml run
```

See [`cloudflared-config.example.yml`](cloudflared-config.example.yml). Run
`cloudflared` itself as a service (`cloudflared service install`) so it's permanent.

## 2. Bridge process supervisor

Keep your bridge/agent process alive with restart-on-crash + backoff:

```bash
agent-os supervise -- python /path/to/your_bridge.py
```

Run it as a service so it starts on boot and restarts the supervisor itself:

- **Linux (systemd):** [`agent-os.service`](agent-os.service) → `systemctl --user enable --now agent-os`
- **macOS (launchd):** [`com.agentos.bridge.plist`](com.agentos.bridge.plist) → `launchctl load ~/Library/LaunchAgents/com.agentos.bridge.plist`

## 3. Health checks

```bash
agent-os health            # human-readable
agent-os health --json     # for monitoring; exit 1 if "down"
```

Wire `agent-os health --json` into your uptime monitor or a systemd healthcheck.

## 4. Sender allowlist

Only act on commands from authorized senders. Put your ids in a file (one per
line, `#` comments allowed) — see [`allowlist.example.txt`](allowlist.example.txt) —
and load it in your gateway:

```python
from agent_os.allowlist import Allowlist
allow = Allowlist(path="agent_state/allowlist.txt")
if not allow.is_allowed(incoming_sender):
    return  # ignore
```

The allowlist **fails closed**: an empty list denies everyone.

## 5. Token health

```python
from agent_os.token_health import check_tokens, render
print(render(check_tokens(["WHATSAPP_TOKEN", "META_APP_SECRET"])))
```

Presence/shape/expiry are checked locally and the value is **never logged**. For
live validation (does the Meta token still work?), pass your own `validator=` —
agent-os does not call the Graph API for you.

## 6. Daily Ninja eval summary

Run a daily reliability summary and send it to yourself:

```bash
agent-os daily-eval                       # prints the summary
agent-os daily-eval | <your notifier>     # e.g. ninja-harness scripts/notify.py
```

Schedule it with cron, a systemd timer, or the GitHub Action in
[`daily-eval.github-action.yml`](daily-eval.github-action.yml). Set
`AGENT_OS_SUITE` to a Ninja Harness suite path to run a real regression suite;
otherwise it summarizes recent job outcomes.
