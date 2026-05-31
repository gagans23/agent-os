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
  #onboard { display:none; border-color: var(--warn); }
  #onboard h2 { color: var(--warn); }
  #onboard pre { background:#0b0e13; border:1px solid var(--line); border-radius:8px;
        padding:12px; white-space:pre-wrap; font-size:12.5px; line-height:1.5; margin:0 0 10px; }
  #onboard code { background:#0b0e13; border:1px solid var(--line); border-radius:6px;
        padding:1px 6px; font-size:12px; }
  /* Live setup progress ("watch the magic") */
  #onboard-live { display:none; }
  .phase { display:flex; align-items:center; gap:10px; font-size:15px; font-weight:600;
           margin:2px 0 12px; }
  .dot { width:10px; height:10px; border-radius:50%; background:var(--accent);
         box-shadow:0 0 0 0 rgba(59,130,246,.7); animation:pulse 1.4s infinite; flex:none; }
  .dot.ok { background:var(--ok); animation:none; box-shadow:none; }
  .dot.err { background:#f85149; animation:none; box-shadow:none; }
  @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(59,130,246,.7);}
                     70%{box-shadow:0 0 0 12px rgba(59,130,246,0);}
                     100%{box-shadow:0 0 0 0 rgba(59,130,246,0);} }
  .bar { height:12px; background:#0b0e13; border:1px solid var(--line);
         border-radius:999px; overflow:hidden; }
  .bar > i { display:block; height:100%; width:0%;
             background:linear-gradient(90deg,#3b82f6,#22d3ee);
             border-radius:999px; transition:width .5s ease; }
  .bar.indet > i { width:35% !important; animation:slide 1.2s ease-in-out infinite; }
  @keyframes slide { 0%{margin-left:-35%;} 100%{margin-left:100%;} }
  .barwrap { display:flex; align-items:center; gap:10px; margin:4px 0 12px; }
  .barwrap .pct { font-variant-numeric:tabular-nums; font-size:13px; color:var(--muted);
                  min-width:42px; text-align:right; }
  .console { background:#0b0e13; border:1px solid var(--line); border-radius:8px;
             padding:10px 12px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
             font-size:12px; line-height:1.55; color:#9fb1c1; max-height:140px;
             overflow:auto; white-space:pre-wrap; word-break:break-word; }
  .steps { display:flex; gap:14px; flex-wrap:wrap; margin:0 0 12px; font-size:12.5px;
           color:var(--muted); }
  .steps b { color:var(--fg); font-weight:600; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🤖 agent-os</h1>
    <span class="sub">your personal agent OS — local, traced, scored, gated</span>
  </header>
  <div id="status">loading…</div>

  <div class="card" id="onboard">
    <h2>🚀 First-time setup — get to a working local model</h2>
    <p class="hint">agent-os works right now in <strong>demo mode</strong> (deterministic,
      no model). Plug in a free local model to make <code>Ask</code> and <code>Run</code>
      smart — one click, no terminal.</p>
    <div id="onboard-ready" style="display:none">
      <button class="primary" id="setup-btn" onclick="setupRun()">⬇️ Pull recommended model &amp; enable</button>
      <span class="hint" id="setup-note" style="margin-left:8px"></span>
    </div>
    <div id="onboard-install" style="display:none">
      <p class="hint">First install <strong>Ollama</strong> (free; a normal app installer —
        no terminal): <a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a>.
        Open it once, then reload this page and click the button.</p>
    </div>

    <!-- Live progress: the user watches the agent set itself up, no terminal. -->
    <div id="onboard-live">
      <div class="phase"><span class="dot" id="live-dot"></span><span id="live-phase">Starting…</span></div>
      <div class="barwrap">
        <div class="bar indet" id="live-bar"><i></i></div>
        <span class="pct" id="live-pct"></span>
      </div>
      <div class="steps" id="live-steps">
        <span data-k="ollama">① Ollama</span>
        <span data-k="model">② Model</span>
        <span data-k="enable">③ Enable</span>
        <span data-k="verify">④ Verify</span>
      </div>
      <div class="console" id="live-log">starting…</div>
    </div>

    <pre id="onboard-steps">checking your machine…</pre>
  </div>

  <div class="row">
    <button onclick="send('/status')">Status</button>
    <button onclick="send('/health')">Health</button>
    <button onclick="send('/agents')">Agents</button>
    <button onclick="send('/skills')">Skills</button>
    <button onclick="send('/model')">Model</button>
    <button onclick="send('/setup')">Setup</button>
    <button onclick="send('/doctor')">Doctor</button>
    <button onclick="send('/cost')">Cost</button>
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
    <h2>🐝 Swarm a goal</h2>
    <p class="hint">Decompose → run sub-tasks in parallel (each traced + scored) →
      synthesize one deliverable. Privileged sub-tasks are gated.</p>
    <div class="flex">
      <input id="swarm" type="text" placeholder="research the top 5 local LLM runtimes; compare in a table"
             onkeydown="if(event.key==='Enter')swarm()" />
      <button class="primary" onclick="swarm()">Swarm</button>
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
function swarm(){ const v=document.getElementById('swarm').value.trim(); if(v) send('/swarm '+v); }

async function api(command){
  const r = await fetch('/api/cmd', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({command})});
  return (await r.json()).output || '';
}

// Populate the status line on load.
api('/status').then(out=>{document.getElementById('status').textContent =
    out.split('\\n').slice(0,2).join('  ·  ');})
  .catch(()=>{document.getElementById('status').textContent='(could not load status)';});

// First-time setup. If a background pull is already running (e.g. the page was
// reloaded mid-download), resume the live view. Otherwise show the empty-state.
function initOnboarding(){
  fetch('/api/setup/status').then(r=>r.json()).then(s=>{
    if (s.state === 'running'){            // resume watching the magic
      document.getElementById('onboard').style.display = 'block';
      enterLiveMode(); renderSetup(s); pollSetup();
      return;
    }
    api('/model').then(out=>{
      if (!out.includes('none configured')) return;    // already set up
      document.getElementById('onboard').style.display = 'block';
      api('/setup').then(steps=>{
        document.getElementById('onboard-steps').textContent = steps;
      });
      // What will one click do? Label the button honestly (instant vs download).
      fetch('/api/setup/plan').then(r=>r.json()).then(p=>{
        const installed = p.ollama_installed !== false;
        document.getElementById('onboard-ready').style.display = installed ? 'block' : 'none';
        document.getElementById('onboard-install').style.display = installed ? 'none' : 'block';
        const btn = document.getElementById('setup-btn');
        const note = document.getElementById('setup-note');
        if (p.model && p.already_present){
          btn.textContent = '⚡ Enable ' + p.model + ' (already downloaded)';
          note.textContent = p.upgrade
            ? 'Instant — already on your machine. Bigger option later: ' + p.upgrade + '.'
            : 'Instant — this model is already on your machine.';
        } else if (p.model){
          btn.textContent = '⬇️ Download & enable ' + p.model;
          note.textContent = 'First download runs in the background — you can watch it here.';
        }
      }).catch(()=>{});
    });
  }).catch(()=>{});
}
initOnboarding();

function enterLiveMode(){
  document.getElementById('onboard-ready').style.display = 'none';
  document.getElementById('onboard-install').style.display = 'none';
  document.getElementById('onboard-steps').style.display = 'none';
  document.getElementById('onboard-live').style.display = 'block';
}

// Map free-text log lines → which of the 4 steps is active, to light them up.
function markSteps(phase, done){
  const order = ['ollama','model','enable','verify'];
  let active = 1;                                   // ② Model by default
  const p = (phase||'').toLowerCase();
  if (p.indexOf('enabl') >= 0) active = 2;
  else if (p.indexOf('verif') >= 0) active = 3;
  else if (p.indexOf('ready') >= 0 || done) active = 4;
  document.querySelectorAll('#live-steps span').forEach((el,i)=>{
    el.innerHTML = el.innerHTML.replace(/^(✅ |▶ )/,'');
    if (i < active) el.innerHTML = '✅ ' + el.innerHTML;
    else if (i === active && !done) el.innerHTML = '▶ ' + el.innerHTML;
  });
}

function renderSetup(s){
  const dot = document.getElementById('live-dot');
  const phaseEl = document.getElementById('live-phase');
  const bar = document.getElementById('live-bar');
  const pctEl = document.getElementById('live-pct');
  const logEl = document.getElementById('live-log');
  phaseEl.textContent = s.phase || 'Working…';
  if (typeof s.pct === 'number'){
    bar.classList.remove('indet');
    bar.firstElementChild.style.width = s.pct + '%';
    pctEl.textContent = s.pct + '%';
  } else if (s.state !== 'running'){
    bar.classList.remove('indet');
    bar.firstElementChild.style.width = (s.state==='error'?0:100) + '%';
    pctEl.textContent = '';
  }
  if (s.lines && s.lines.length){ logEl.textContent = s.lines.join('\\n'); logEl.scrollTop = logEl.scrollHeight; }
  dot.className = 'dot' + (s.state==='done'?' ok':s.state==='error'?' err':'');
  markSteps(s.phase, s.state!=='running');
  if (s.state === 'done'){
    if (s.verified || (s.model_present !== false && s.persisted)){
      phaseEl.textContent = '✅ Ready — ' + (s.provider || 'model enabled') + '. Reloading…';
      setTimeout(()=>location.reload(), 1800);
    } else if (s.ollama_installed === false){
      document.getElementById('onboard-live').style.display = 'none';
      document.getElementById('onboard-install').style.display = 'block';
    } else {
      phaseEl.textContent = 'Setup didn\\'t finish — see the log below.';
    }
  } else if (s.state === 'error'){
    phaseEl.textContent = 'Error: ' + (s.error || 'unknown');
  }
}

let setupTimer = null;
function pollSetup(){
  if (setupTimer) return;
  setupTimer = setInterval(()=>{
    fetch('/api/setup/status').then(r=>r.json()).then(s=>{
      renderSetup(s);
      if (s.state === 'done' || s.state === 'error'){ clearInterval(setupTimer); setupTimer = null; }
    }).catch(()=>{});
  }, 700);
}

// One-click, no-terminal model setup: start the background pull, then watch it.
async function setupRun(){
  document.getElementById('setup-btn').disabled = true;
  enterLiveMode();
  document.getElementById('live-phase').textContent = 'Starting…';
  document.getElementById('live-log').textContent = 'starting…';
  try {
    const r = await fetch('/api/setup', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({})});
    const s = await r.json();
    if (s.error){ document.getElementById('live-phase').textContent = 'Setup failed: ' + s.error; return; }
    renderSetup(s); pollSetup();
  } catch(e){ document.getElementById('live-phase').textContent = 'Request failed: ' + e; }
}
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
            elif path == "/api/setup/status":
                # Fast, in-memory poll of the background setup job (no blocking).
                self._send(200, json.dumps(router.onboarding_status()))
            elif path == "/api/setup/plan":
                # Read-only preview so the button can be labeled honestly
                # (instant enable vs. download). Diagnoses hardware; changes nothing.
                try:
                    self._send(200, json.dumps(router.onboarding_plan()))
                except Exception as exc:  # noqa: BLE001 - never break page load
                    self._send(200, json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            path = urlparse(self.path).path
            if path not in ("/api/cmd", "/api/setup"):
                self._send(404, json.dumps({"error": "not found"}))
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                body = json.loads(raw or "{}")
            except ValueError:
                self._send(400, json.dumps({"error": "invalid JSON body"}))
                return
            if path == "/api/setup":
                # Explicit user action: pull the recommended model + remember the
                # choice (no terminal). Starts a BACKGROUND job and returns at once;
                # the UI polls /api/setup/status for live progress so the request
                # never blocks on a multi-GB download. Never installs Ollama itself.
                model = (str(body.get("model") or "").strip() or None)
                try:
                    self._send(200, json.dumps(router.start_onboarding(model)))
                except Exception as exc:  # noqa: BLE001 - report, don't crash the UI
                    self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                return
            command = str(body.get("command", "")).strip()
            if not command:
                self._send(400, json.dumps({"error": "empty command"}))
                return
            # The router has its own error boundary, so this never raises.
            self._send(200, json.dumps({"output": router.handle(command, actor="webui")}))

        def log_message(self, *args) -> None:  # silence default request logging
            pass

    return Handler


def _bind(host: str, port: int, tries: int = 20) -> http.server.HTTPServer:
    """Bind to `port`, or the next free one if it's taken (a stale instance is the
    most common reason `agent-os ui` 'doesn't work'). Port 0 = let the OS choose."""
    last: OSError | None = None
    for candidate in range(port, port + tries) if port else [0]:
        try:
            return http.server.HTTPServer((host, candidate),
                                          http.server.BaseHTTPRequestHandler)
        except OSError as exc:  # address already in use
            last = exc
            if candidate != port:
                continue
            print(f"  port {candidate} is busy — trying {candidate + 1}…")
    raise OSError(f"could not bind a port near {port} on {host}: {last}")


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

    httpd = _bind(host, port)
    httpd.RequestHandlerClass = _make_handler(router)
    url = f"http://{host}:{httpd.server_address[1]}/"
    if on_ready is not None:
        on_ready(httpd)
    else:
        bar = "─" * 52
        print(f"\n{bar}\n  agent-os UI is running\n  →  {url}\n"
              f"  Open that link in your browser.  (Ctrl-C to stop)\n{bar}\n",
              flush=True)
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
