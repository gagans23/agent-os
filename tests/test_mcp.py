"""Tests for the MCP connector bridge (stdlib stdio client + config + registry).

End-to-end against a real child process (tests/mcp_fake_server.py) so the JSON-RPC
handshake, framing, and lifecycle are actually exercised — no mocking the wire."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agent_os.mcp import (
    MCPClient,
    MCPError,
    MCPRegistry,
    MCPServerConfig,
    load_servers,
    mcp_config_path,
)

FAKE = Path(__file__).parent / "mcp_fake_server.py"


def _config(name: str = "fake") -> MCPServerConfig:
    return MCPServerConfig(name=name, command=[sys.executable, str(FAKE)])


def _write_mcp_json(path: Path, *, as_string: bool = False) -> Path:
    cmd = f"{sys.executable} {FAKE}" if as_string else [sys.executable, str(FAKE)]
    path.write_text(json.dumps({"servers": {"fake": {"command": cmd}}}))
    return path


# --- client ----------------------------------------------------------------


def test_client_handshake_list_and_call() -> None:
    with MCPClient(_config(), timeout=10) as client:
        tools = {t["name"] for t in client.list_tools()}
        assert {"read_note", "write_note"} <= tools
        out = client.call_tool("read_note", {"q": "hi"})
        assert out == "note says: hi"


def test_client_call_tool_with_mutation() -> None:
    with MCPClient(_config(), timeout=10) as client:
        assert client.call_tool("write_note", {"text": "x"}) == "wrote: x"


def test_client_surfaces_server_error() -> None:
    with MCPClient(_config(), timeout=10) as client:
        with pytest.raises(MCPError):
            client.call_tool("boom", {})


def test_client_missing_command_raises_mcp_error() -> None:
    bad = MCPServerConfig(name="nope", command=["definitely-not-a-real-binary-xyz"])
    with pytest.raises(MCPError):
        MCPClient(bad, timeout=5).start()


def test_client_rejects_non_stdio_transport() -> None:
    cfg = MCPServerConfig(name="http", command=["x"], transport="http")
    with pytest.raises(MCPError):
        MCPClient(cfg).start()


# --- config loading --------------------------------------------------------


def test_load_servers_missing_file_is_empty(tmp_path) -> None:
    assert load_servers(tmp_path / "absent.json") == {}


def test_load_servers_parses_list_and_string_commands(tmp_path) -> None:
    p = _write_mcp_json(tmp_path / "mcp.json", as_string=True)
    servers = load_servers(p)
    assert "fake" in servers
    assert servers["fake"].command[0] == sys.executable  # shell-split worked


def test_load_servers_ignores_malformed(tmp_path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text("{ not valid json")
    assert load_servers(p) == {}


def test_mcp_config_path_honors_agent_os_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
    assert mcp_config_path() == tmp_path / "mcp.json"


# --- registry --------------------------------------------------------------


def test_registry_lists_and_calls(tmp_path) -> None:
    p = _write_mcp_json(tmp_path / "mcp.json")
    reg = MCPRegistry(p, timeout=10)
    assert reg.names() == ["fake"]
    assert {t["name"] for t in reg.list_tools("fake")} >= {"read_note", "write_note"}
    assert reg.call("fake", "read_note", {"q": "yo"}) == "note says: yo"


def test_registry_unknown_server_raises(tmp_path) -> None:
    reg = MCPRegistry(_write_mcp_json(tmp_path / "mcp.json"))
    with pytest.raises(MCPError):
        reg.call("ghost", "read_note", {})
