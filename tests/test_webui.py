"""Tests for the local web UI (stdlib http.server)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from agent_os.webui import PAGE, serve


@pytest.fixture
def server(tmp_path):
    """Run the UI on an ephemeral port in a background thread.

    The router (and its SQLite connections) is built inside `serve`, which runs
    in this thread, so request handling touches sqlite from the same thread."""
    box: dict = {}
    ready = threading.Event()

    def on_ready(httpd):
        box["httpd"] = httpd
        box["port"] = httpd.server_address[1]
        ready.set()

    t = threading.Thread(
        target=lambda: serve(
            host="127.0.0.1", port=0,
            state_dir=str(tmp_path / "state"), skills_dir="skills",
            traces_dir=str(tmp_path / "traces"), open_browser=False, on_ready=on_ready,
        ),
        daemon=True,
    )
    t.start()
    assert ready.wait(5), "server did not start"
    yield box["port"]
    box["httpd"].shutdown()
    t.join(5)


def _post(port: int, command: str):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/cmd",
        data=json.dumps({"command": command}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_page_contains_expected_elements() -> None:
    assert "agent-os" in PAGE
    assert "/api/cmd" in PAGE and "Teach the brain" in PAGE
    # The no-terminal first-time setup affordances are present.
    assert "/api/setup" in PAGE and "Pull recommended model" in PAGE


def test_api_setup_pulls_and_persists(server, monkeypatch) -> None:
    # The 'Pull model' button hits /api/setup → router.run_onboarding(). Stub the
    # actual pull so no real `ollama` runs; assert the endpoint returns its result.
    from agent_os import onboarding
    from agent_os.onboarding import SetupResult

    def fake_run_setup(*, execute, model=None, writer=print, **k):
        writer("pulling…")
        return SetupResult(
            recommended="llama3.2:3b", provider_spec="ollama:llama3.2:3b",
            ollama_installed=True, ollama_running=True, model_present=True,
            executed=True, persisted_to="/tmp/config.json", verified=True,
            steps=["model-pulled", "persisted", "verified"],
        )

    monkeypatch.setattr(onboarding, "run_setup", fake_run_setup)
    req = urllib.request.Request(
        f"http://127.0.0.1:{server}/api/setup",
        data=json.dumps({}).encode(), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read())
    assert r.status == 200
    assert body["verified"] is True and body["persisted"] is True
    assert "pulling…" in body["output"]


def test_serves_index(server) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{server}/", timeout=5) as r:
        html = r.read().decode()
    assert r.status == 200 and "agent-os" in html


def test_api_runs_command(server) -> None:
    status, body = _post(server, "/ping")
    assert status == 200
    assert "pong" in body["output"].lower()


def test_api_learn_and_ask_through_ui(server) -> None:
    _post(server, "/learn To add fractions with the same denominator, add the numerators.")
    _, body = _post(server, "/ask how do I add fractions")
    assert "numerator" in body["output"].lower() or "fraction" in body["output"].lower()


def test_api_rejects_empty_command(server) -> None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{server}/api/cmd",
        data=json.dumps({"command": "  "}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400


def test_unknown_path_404(server) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{server}/nope", timeout=5)
    assert exc.value.code == 404
