# MCP connector bridge

Wire real tools into agent-os through the open
[Model Context Protocol](https://modelcontextprotocol.io) (MCP) — filesystem,
GitHub, databases, browsers, and the growing ecosystem of MCP servers — **behind
the agent-os spine**. Every call is risk-gated (default-deny), traced, scored,
and audited, exactly like any other job.

This is Module 4's "mix in the best, don't reinvent" in action: agent-os doesn't
re-implement those tools, it speaks their standard protocol and governs the calls.

## Principles it keeps

- **Pluggable, never faked.** agent-os bundles **no** MCP server and stores **no**
  credentials. You declare your own servers; with none declared the bridge is
  inert. Your secrets live in *your* config file, passed to the child process —
  never in agent-os.
- **Local-first, dependency-light.** The MCP *stdio* transport (newline-delimited
  JSON-RPC 2.0 over a child process's stdin/stdout) is implemented in
  [`agent_os/mcp.py`](../agent_os/mcp.py) with **only the standard library** —
  no MCP SDK, no new runtime dependency.
- **Default-deny autonomy.** *Listing* servers and tools is read-only and
  auto-runs. *Calling* a tool is classified by the same tool-aware risk engine
  ([`risk.py`](../agent_os/risk.py)): a read-only tool auto-runs; a tool that
  writes/sends/deploys — or one whose intent is ambiguous — needs `/approve`.
- **Traced · scored · audited.** Each call runs through `run_job`, so it produces
  a trace, a Ninja-Harness score, a persisted job record, and an audit-log entry.

## Configure your servers

Declare servers in `~/.agent-os/mcp.json` (override the base dir with
`AGENT_OS_HOME`):

```json
{
  "servers": {
    "filesystem": {
      "command": ["npx", "-y",
                  "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "github": {
      "command": "npx -y @modelcontextprotocol/server-github",
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_…"}
    }
  }
}
```

- `command` — a list (preferred) or a string (shell-split). The argv that launches
  the server. You install/run those servers yourself; agent-os only speaks to them.
- `env` — merged onto the environment of the **child process only**. This is where
  a server's own credentials go. agent-os never reads or logs them.
- `cwd` — optional working directory for the server.

A starter you can copy: [`examples/mcp.json`](../examples/mcp.json).

## Use it

All commands work in the local web UI, over `agent-os cmd "…"`, and through any
transport the router is wired to.

```text
/mcp                              list your configured servers
/mcp-tools filesystem            list a server's tools (+ each tool's gate)
/mcp-call filesystem read_file {"path": "/etc/hostname"}     # read → auto-runs
/mcp-call filesystem write_file {"path": "/tmp/x", "content": "hi"}  # write → needs approval
```

A gated call replies with an approval id:

```text
⛔ Needs approval — MCP WRITE (WRITE: matched tool:write).
Server: filesystem   Tool: write_file
Approve:  /approve 1a2b3c4d
Reject:   /reject 1a2b3c4d
```

`/approve <id>` then executes the *exact* stored call through `run_job` (traced +
scored + persisted), and `/reject <id>` discards it. Nothing privileged runs
without that explicit human decision.

`/mcp-tools` previews the gate per tool so there are no surprises:

```text
Tools on 'filesystem' (risk gate previewed per tool):
  read_file   [READ_ONLY → auto-run]   — Read a file's contents.
  write_file  [WRITE → needs approval] — Write/overwrite a file.
  list_dir    [READ_ONLY → auto-run]   — List a directory.
```

## How the gate decides

The tool *name* is fed to the tool-aware risk classifier. A name containing a
write/send/deploy signal (`write`, `delete`, `send`, `publish`, …) escalates the
call to needing approval — because **capability, not phrasing, is what's
dangerous**. A clearly read-only name (`read`, `list`, `get`, `search`, …)
auto-runs. Anything else falls to **default-deny** and needs approval. You can
swap in your own policy with `CommandRouter(policy=…)`; the gate still runs on
every call.

## Programmatic use

```python
from agent_os import MCPRegistry

reg = MCPRegistry()                       # reads ~/.agent-os/mcp.json
print(reg.names())                        # ['filesystem', 'github']
tools = reg.list_tools("filesystem")      # [{'name': 'read_file', ...}, ...]
out = reg.call("filesystem", "read_file", {"path": "/etc/hostname"})
```

`MCPRegistry` opens a short-lived stdio connection per call and closes it — simple
and robust, no long-lived child processes to leak. For finer control, use
`MCPClient` directly as a context manager.

## Scope / what's next

- **Transport:** `stdio` today (the common case). HTTP/SSE transports are a natural
  follow-up; the client raises a clear `MCPError` for any non-stdio transport.
- **Role packs** will ship curated `mcp.json` + skills bundles (a non-technical
  productivity pack; a pro-coder dev pack), every command still flowing through the
  governed router.

See also: [roadmap](roadmap.md) · [architecture](architecture.md) ·
[risk & approvals](architecture.md) · [compose your own](extending.md).
