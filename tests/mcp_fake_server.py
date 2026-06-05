"""A tiny, self-contained MCP server for tests (stdio, newline-delimited JSON-RPC).

Not a test module itself (no ``test_`` prefix, so pytest won't collect it). It is
launched as a child process by the MCP client tests via ``sys.executable``.

Tools:
  read_note   — read-only (name has a read verb) → auto-runs through the gate
  write_note  — write (name has a write verb)    → needs approval
  boom        — always returns a JSON-RPC error  → exercises MCPError handling
"""

from __future__ import annotations

import json
import sys


def _reply(mid, result) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


def _error(mid, code, message) -> None:
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})
        + "\n"
    )
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            _reply(mid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "0"},
            })
        elif method == "notifications/initialized":
            continue  # a notification — no response
        elif method == "tools/list":
            _reply(mid, {"tools": [
                {"name": "read_note", "description": "Read a note (safe)."},
                {"name": "write_note", "description": "Write a note (mutating)."},
            ]})
        elif method == "tools/call":
            params = msg.get("params", {}) or {}
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            if name == "read_note":
                _reply(mid, {"content": [{"type": "text", "text": f"note says: {args.get('q', '?')}"}]})
            elif name == "write_note":
                _reply(mid, {"content": [{"type": "text", "text": f"wrote: {args.get('text', '')}"}]})
            elif name == "boom":
                _error(mid, -32000, "kaboom")
            else:
                _error(mid, -32601, f"unknown tool: {name}")
        elif mid is not None:
            _error(mid, -32601, f"unknown method: {method}")


if __name__ == "__main__":
    main()
