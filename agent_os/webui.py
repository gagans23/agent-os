"""
webui — a minimal local web UI for agent-os (Module 3, the "click a button" goal).

Standard-library only (`http.server`) — no Flask/FastAPI, nothing to install. It
serves one page that drives the same `CommandRouter` as the CLI and WhatsApp
surface, so **all governance still applies**: every action is audited, and
write/send/deploy tasks are risk-gated for approval.

Local-first & private by default: binds to 127.0.0.1. Do not expose it to a
network without putting your own auth in front of it.

    agent-os ui                      # open http://127.0.0.1:8765 in your browser
"""

from __future__ import annotations

import http.server
import json
import threading
import webbrowser
from collections.abc import Callable
from urllib.parse import urlparse

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>agent-os</title>
<style>
  :root { --bg:#0e1116; --card:#171b22; --line:#262c36; --fg:#e6edf3;
          --muted:#8b949e; --accent:#3b82f6; --ok:#2ea043; --warn:#d29922; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 28px 18px 60px; }
  header { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  h1 { font-size: 26px; margin: 0; }
  .sub { color: var(--muted); font-size: 14px; }
  #status { color: var(--muted); font-size: 13px; margin: 8px 0 20px;
            white-space: pre-wrap; }
  .row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom: 18px; }
  button { background:var(--card); color:var(--fg); border:1px solid var(--line);
           border-radius:8px; padding:8px 12px; cursor:pointer; font-size:13px; }
  button:hover { border-color: var(--accent); }
  button.primary { background: var(--accent); border-color: var(--accent); color:#fff; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:16px; margin-bottom:14px; }
  .card h2 { font-size:14px; margin:0 0 10px; color:var(--fg); }
  .card .hint { color:var(--muted); font-size:12px; margin:0 0 10px; }
  input[type=text], textarea { width:100%; background:var(--bg); color:var(--fg);
    border:1px solid var(--line); border-radius:8px; padding:10px; font-size:14px;
    font-family:inherit; resize:vertical; }
  .flex { display:flex; gap:8px; }
  .flex input { flex:1; }
  pre { background:#0b0e13; border:1px solid var(--line); border-radius:10px;
        padding:14px; overflow:auto; min-height:90px; white-space:pre-wrap;
        word-break:break-word; font-size:13px; line-height:1.45; }
  .muted { color: var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🤖 agent-os</h1>
    <span class="sub">your personal agent OS — local, traced, scored, gated</span>
  </header>
  <div id="status">loading…</div>

  <div class="row">
    <button onclick="send('/status')">Status</button>
    <button onclick="send('/health')">Health</button>
    <button onclick="send('/agents')">Agents</button>
    <button onclick="send('/skills')">Skills</button>
    <button onclick="send('/model')">Model</button>
    <button onclick="send('/audit')">Audit</button>
    <button onclick="send('/pending')">Pending</button>
    <button onclick="send('/digest')">Digest</button>
    <button onclick="send('/browser-demo')">Browser demo</button>
  </div>

  <div class="card">
    <h2>🧠 Teach the brain</h2>
    <p class="hint">Paste notes (or a file path on this machine). Ingested into your
      local knowledge base.</p>
    <textarea id="learn" rows="3" placeholder="e.g. To add fractions with the same denominator, add the numerators."></textarea>
    <div style="height:8px"></div>
    <button class="primary" onclick="learn()">Learn</button>
  </div>

  <div class="card">
    <h2>❓ Ask your brain</h2>
    <p class="hint">Answered <em>only</em> from what you've taught it, and scored for grounding.</p>
    <div class="flex">
      <input id="ask" type="text" placeholder="how do I add fractions?"
             onkeydown="if(event.key==='Enter')ask()" />
      <button class="primary" onclick="ask()">Ask</button>
    </div>
  </div>

  <div class="card">
    <h2>⚙️ Run a task</h2>
    <p class="hint">Read-only tasks auto-run; anything that writes/sends/deploys is
      gated for approval (see Pending).</p>
    <div class="flex">
      <input id="run" type="text" placeholder="summarize the latest research"
             onkeydown="if(event.key==='Enter')run()" />
      <button class="primary" onclick="run()">Run</button>
    </div>
  </div>

  <div class="card">
    <h2>&gt;_ Command</h2>
    <div class="flex">
      <input id="cmd" type="text" placeholder="/help"
             onkeydown="if(event.key==='Enter')sendInput()" />
      <button onclick="sendInput()">Send</button>
    </div>
  </div>

  <pre id="out" class="muted">Output appears here. Try a quick action above, or type /help.</pre>
</div>

<script>
async function send(command) {
  const out = document.getElementById('out');
  out.classList.remove('muted');
  out.textContent = '$ ' + command + '\\n…';
  try {
    const r = await fetch('/api/cmd', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({command})});
    const j = await r.json();
    out.textContent = '$ ' + command + '\\n\\n' + (j.output || j.error || '(no output)');
  } catch (e) { out.textContent = 'Request failed: ' + e; }
}
function sendInput(){ const v=document.getElementById('cmd').value.trim(); if(v) send(v); }
function learn(){ const v=document.getElementById('learn').value.trim(); if(v) send('/learn '+v); }
function ask(){ const v=document.getElementById('ask').value.trim(); if(v) send('/ask '+v); }
function run(){ const v=document.getElementById('run').value.trim(); if(v) send('/run '+v); }

// Populate the status line on load.
fetch('/api/cmd', {method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({command:'/status'})})
  .then(r=>r.json()).then(j=>{document.getElementById('status').textContent =
    (j.output||'').split('\\n').slice(0,2).join('  ·  ');})
  .catch(()=>{document.getElementById('status').textContent='(could not load status)';});
</script>
</body>
</html>"""


def _make_handler(router) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body, ctype: str = "application/json") -> None:
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if urlparse(self.path).path != "/api/cmd":
                self._send(404, json.dumps({"error": "not found"}))
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                command = str(json.loads(raw or "{}").get("command", "")).strip()
            except (ValueError, AttributeError):
                self._send(400, json.dumps({"error": "invalid JSON body"}))
                return
            if not command:
                self._send(400, json.dumps({"error": "empty command"}))
                return
            # The router has its own error boundary, so this never raises.
            self._send(200, json.dumps({"output": router.handle(command, actor="webui")}))

        def log_message(self, *args) -> None:  # silence default request logging
            pass

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, *, router=None,
          state_dir: str = "agent_state", skills_dir: str = "skills",
          traces_dir: str = "traces", suite: str | None = None,
          open_browser: bool = True,
          on_ready: Callable[[http.server.HTTPServer], None] | None = None) -> None:
    """Run the local web UI (blocking). If `router` is None, one is built here so
    its SQLite connections live in the serving thread."""
    own_router = router is None
    if router is None:
        from agent_os.agent_memory import AgentMemory
        from agent_os.command_router import CommandRouter
        from agent_os.jobs import JobStore
        from agent_os.skill_registry import SkillRegistry, skill_roots_from_env
        from agent_os.trace_recorder import TraceRecorder

        router = CommandRouter(
            jobs=JobStore(f"{state_dir}/jobs.db"),
            memory=AgentMemory(state_dir),
            skills=SkillRegistry(skill_roots_from_env(skills_dir)),
            recorder=TraceRecorder(traces_dir),
            suite_path=suite,
        )

    httpd = http.server.HTTPServer((host, port), _make_handler(router))
    url = f"http://{host}:{httpd.server_address[1]}/"
    if on_ready is not None:
        on_ready(httpd)
    else:
        print(f"agent-os UI → {url}   (Ctrl-C to stop)")
        if open_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if own_router:
            router.close()
