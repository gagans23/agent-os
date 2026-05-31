# Run agent-os without the terminal

agent-os is built so a non-technical person can get to a working local agent
**without typing a single command**. There are two parts, and both are
click-only:

1. **Start agent-os** — double-click a launcher (below).
2. **Get a model** — click one button in the web UI (no terminal).

> Honest note: the very first time, a small setup window appears while a local
> environment is created (a couple of minutes). You don't type anything in it —
> it just shows progress, then your browser opens. After that, launching is
> instant.

---

## 1. Start agent-os (double-click)

Download the agent-os folder, then double-click the launcher for your system —
it lives in the **`launchers/`** folder. Keep it inside the agent-os folder.

| System  | Double-click                          |
|---------|----------------------------------------|
| macOS   | `launchers/agent-os.app`               |
| Windows | `launchers/agent-os-windows.bat`       |
| Linux   | `launchers/agent-os-linux.sh`          |

The launcher sets things up on first run, then opens
**http://127.0.0.1:8765** in your browser. To stop agent-os, close the window.

> **macOS: use `agent-os.app`, not the `.command`.** Finder launches a `.app`
> reliably. A bare `.command` relies on a file-type association that is often
> missing, in which case double-clicking it does **nothing at all** (no window,
> no error). `agent-os.app` is a tiny, fully-readable wrapper (a plist + a shell
> script you can open and inspect) that simply runs the `.command` for you in a
> progress window. `launchers/agent-os-macos.command` is still there as a
> fallback if you prefer running it directly.

### First-launch security prompts (normal for any downloaded app)

- **macOS**: because `agent-os.app` is built from *your own* downloaded folder
  (not a packaged download), it normally opens without a Gatekeeper prompt. If
  macOS ever says a file is "from an unidentified developer," right-click (or
  Control-click) it → **Open** → **Open**. You only do this once. (agent-os
  isn't code-signed with an Apple Developer certificate — see "Why not a single
  app?" below.)
- **Windows** may show a SmartScreen notice → **More info** → **Run anyway**.
- **Linux**: some file managers need *Properties → Permissions → Allow executing
  as program* before a double-click runs the `.sh`.

### What the launcher needs present

- **Python 3.11+** and **Git**. If they're missing, the launcher opens the right
  download page (Python from python.org, Git from git-scm.com) — both are normal
  click-through installers, no terminal. Install, then double-click the launcher
  again.

---

## 2. Get a model (one click in the UI)

agent-os works immediately in **demo mode** (deterministic, no model). To make
`Ask` and `Run` smart, plug in a free local model — no terminal:

1. In the UI, the first-time setup card shows a single button. It's labeled
   honestly for your machine:
   - **"⚡ Enable <model> (already downloaded)"** if you already have a capable
     model — one click, instant, no download.
   - **"⬇️ Download & enable <model>"** otherwise — the download runs in the
     **background** and you **watch it live** (progress bar + step checklist +
     log), so nothing freezes and you can keep using agent-os meanwhile.
2. agent-os detects [Ollama](https://ollama.com), enables the model, verifies it,
   remembers the choice, and reloads — now smart. (If a bigger, higher-quality
   model suits your machine, it's offered as an optional upgrade — never forced.)
3. If Ollama isn't installed, the card links its normal app installer (a regular
   click-through installer). Install it, reload, and click the button.

> Why it streams: pulling a model can be several GB. agent-os runs the pull as a
> background job and the page polls for progress, so a non-technical user sees it
> working in real time instead of a spinner that looks stuck.

agent-os **never installs Ollama for you** — that stays your explicit click, by
design (it's the one piece of system software involved).

---

## Why not a fully self-contained signed app (.app / .exe)?

`agent-os.app` above is a thin, local wrapper — it still uses the Python in your
folder. A **packaged, signed** application that bundles everything and needs
*nothing* pre-installed is the natural next step. It isn't shipped yet because
distributing one without scary security warnings requires **code-signing /
notarization** with an Apple Developer or Microsoft certificate — that's tied to
a developer account and can't be bundled into an open-source repo. The launchers
above are the signing-free path that works today.

If you maintain your own build, you can wrap the launcher with PyInstaller /
py2app and sign it with your certificate — agent-os stays a normal Python
package underneath.

---

## The same thing from a terminal (for developers)

```bash
./install.sh        # one-time setup (venv + eval gate + agent-os)
agent-os setup --run  # pull a model + remember it (optional)
agent-os ui         # open the web UI
```
