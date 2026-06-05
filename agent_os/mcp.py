"""
mcp — a minimal, dependency-free bridge to Model Context Protocol (MCP) servers.

MCP is the open standard that lets agents reach real tools (filesystem, GitHub,
databases, browsers, …) through a uniform JSON-RPC interface. This module wires
those tools in behind the agent-os spine, **true to the core principles**:

* **Pluggable, never faked.** agent-os bundles **no** MCP server and stores **no**
  credentials. You declare your own servers in ``~/.agent-os/mcp.json`` (override
  the base dir with ``AGENT_OS_HOME``). With none configured, the bridge is inert.
* **Local-first, dependency-light.** The MCP *stdio* transport — newline-delimited
  JSON-RPC 2.0 over a child process's stdin/stdout — is implemented here with only
  the standard library (``subprocess`` + ``json`` + ``threading``). No MCP SDK.
* **Default-deny autonomy.** This module only *connects, lists, and calls*. The
  router (``command_router``) routes every call through the risk gate: listing is
  read-only and auto-runs; a tool that writes/sends/deploys needs human approval.
  Calls are traced, scored, and audited like any other job.

Config format (``~/.agent-os/mcp.json``)::

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

``command`` may be a list (preferred) or a string (shell-split). ``env`` is merged
onto the current environment for the child process only — secrets live in *your*
file, never in agent-os.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from agent_os import __version__

# The MCP protocol revision we speak during the handshake. Servers negotiate and
# generally accept a slightly different revision; we send a known-good baseline.
PROTOCOL_VERSION = "2024-11-05"

_READER_DEAD = object()  # sentinel pushed when the server's stdout closes (EOF)


class MCPError(RuntimeError):
    """Any failure talking to an MCP server (spawn, transport, timeout, or a
    JSON-RPC error object returned by the server)."""


# --- configuration ---------------------------------------------------------


@dataclass
class MCPServerConfig:
    """One user-declared MCP server. ``command`` is the argv that launches it."""

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    transport: str = "stdio"


def mcp_config_path() -> Path:
    """Where the user's MCP server declarations live. Mirrors providers.config_path
    so ``AGENT_OS_HOME`` relocates all agent-os state together."""
    base = os.environ.get("AGENT_OS_HOME")
    return (Path(base) if base else Path.home() / ".agent-os") / "mcp.json"


def load_servers(path: str | Path | None = None) -> dict[str, MCPServerConfig]:
    """Load declared servers. Returns ``{}`` if the file is absent or malformed —
    a missing config is a normal state (the bridge is simply inert), never an error."""
    p = Path(path) if path else mcp_config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    servers: dict[str, MCPServerConfig] = {}
    for name, spec in (data.get("servers") or {}).items():
        if not isinstance(spec, dict):
            continue
        cmd = spec.get("command")
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        if not cmd or not isinstance(cmd, list):
            continue
        servers[name] = MCPServerConfig(
            name=name,
            command=[str(c) for c in cmd],
            env={str(k): str(v) for k, v in (spec.get("env") or {}).items()},
            cwd=spec.get("cwd"),
            transport=str(spec.get("transport", "stdio")),
        )
    return servers


# --- the stdio JSON-RPC client ---------------------------------------------


def _content_text(result: dict) -> str:
    """Flatten an MCP ``tools/call`` result's content blocks into plain text."""
    parts: list[str] = []
    for item in result.get("content", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        else:  # image/resource/etc. — note its presence without dumping bytes
            parts.append(f"[{item.get('type', 'content')}]")
    text = "\n".join(p for p in parts if p)
    if result.get("isError"):
        text = f"ERROR: {text}" if text else "ERROR (tool reported failure)"
    return text


class MCPClient:
    """A single connection to one MCP server over stdio.

    Usage::

        with MCPClient(config) as client:
            tools = client.list_tools()
            out = client.call_tool("read_file", {"path": "/etc/hostname"})

    One request is in flight at a time (the bridge is synchronous by design).
    A background reader thread parses newline-delimited JSON-RPC messages so a
    slow or chatty server can't deadlock the writer.
    """

    def __init__(self, config: MCPServerConfig, *, timeout: float = 30.0) -> None:
        self.config = config
        self.timeout = timeout
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._q: queue.Queue = queue.Queue()
        self._id = 0
        self._started = False

    # context manager -------------------------------------------------------

    def __enter__(self) -> MCPClient:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # lifecycle -------------------------------------------------------------

    def start(self) -> MCPClient:
        if self._started:
            return self
        if self.config.transport != "stdio":
            raise MCPError(
                f"unsupported transport '{self.config.transport}' "
                f"(only 'stdio' is implemented)"
            )
        env = os.environ.copy()
        env.update(self.config.env)
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - argv from the user's own config
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=env,
                cwd=self.config.cwd,
            )
        except FileNotFoundError as exc:
            raise MCPError(
                f"could not launch MCP server '{self.config.name}': "
                f"command not found: {self.config.command[0]}"
            ) from exc
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # JSON-RPC handshake: initialize, then the initialized notification.
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "agent-os", "version": __version__},
            },
        )
        self._notify("notifications/initialized")
        self._started = True
        return self

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._proc = None
        self._started = False

    # public API ------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """Return the server's tools: dicts with ``name``/``description``/``inputSchema``."""
        result = self._request("tools/list", {})
        tools = result.get("tools", [])
        return [t for t in tools if isinstance(t, dict)]

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """Invoke a tool and return its flattened text content. Raises MCPError on
        a transport/protocol error; a tool that *reports* failure returns text
        prefixed with ``ERROR:`` (so callers can still trace the response)."""
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return _content_text(result)

    # transport -------------------------------------------------------------

    def _read_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                continue  # ignore non-JSON noise on the wire
        self._q.put(_READER_DEAD)

    def _send(self, obj: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise MCPError("MCP server is not running")
        try:
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"MCP server '{self.config.name}' closed the connection") from exc

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        req_id = self._id
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return self._await(req_id)

    def _await(self, req_id: int) -> dict:
        import time

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"timed out waiting for '{self.config.name}' response")
            try:
                msg = self._q.get(timeout=remaining)
            except queue.Empty:
                raise MCPError(f"timed out waiting for '{self.config.name}' response") from None
            if msg is _READER_DEAD:
                raise MCPError(f"MCP server '{self.config.name}' exited unexpectedly")
            if not isinstance(msg, dict) or msg.get("id") != req_id:
                continue  # a notification or server→client request — not our reply
            if "error" in msg:
                err = msg["error"] or {}
                raise MCPError(f"{err.get('message', 'error')} (code {err.get('code', '?')})")
            return msg.get("result", {}) or {}


# --- the registry ----------------------------------------------------------


class MCPRegistry:
    """Loads the user's declared servers and connects on demand. Each ``list_tools``
    / ``call`` opens a fresh short-lived connection and closes it — simple and
    robust for a synchronous, governed bridge (no long-lived child processes)."""

    def __init__(self, path: str | Path | None = None, *, timeout: float = 30.0) -> None:
        self.path = Path(path) if path else mcp_config_path()
        self.timeout = timeout
        self.servers = load_servers(self.path)

    def reload(self) -> None:
        self.servers = load_servers(self.path)

    def names(self) -> list[str]:
        return sorted(self.servers)

    def get(self, name: str) -> MCPServerConfig | None:
        return self.servers.get(name)

    def list_tools(self, name: str) -> list[dict]:
        config = self._require(name)
        with MCPClient(config, timeout=self.timeout) as client:
            return client.list_tools()

    def call(self, name: str, tool: str, arguments: dict | None = None) -> str:
        config = self._require(name)
        with MCPClient(config, timeout=self.timeout) as client:
            return client.call_tool(tool, arguments or {})

    def _require(self, name: str) -> MCPServerConfig:
        config = self.servers.get(name)
        if config is None:
            raise MCPError(f"no MCP server named '{name}' is configured")
        return config
