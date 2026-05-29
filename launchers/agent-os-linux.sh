#!/bin/bash
#
# agent-os — double-click (or run) to start (Linux).
#
# Keep this file inside the agent-os folder. The first run sets up a small local
# environment; every run after that just opens the web UI in your browser. You
# don't type anything. To stop agent-os, close this window / press Ctrl-C.
#
# Tip: some file managers need you to mark this "Allow executing as program"
# (Properties → Permissions) before a double-click will run it.

cd "$(dirname "$0")/.." || exit 1

echo "🤖  Starting agent-os…"
echo

if [ ! -x ".venv/bin/agent-os" ]; then
  echo "First run: setting up a local environment. This can take a couple of minutes…"
  echo
  if ! ./install.sh; then
    echo
    echo "Setup needs Python 3.11+ (and git). Install them, then run this again."
    xdg-open "https://www.python.org/downloads/" 2>/dev/null || true
    read -r -p "Press Return to close." _ || true
    exit 1
  fi
fi

echo
echo "Opening the web UI in your browser…   (Ctrl-C or close this window to stop)"
exec .venv/bin/agent-os ui "$@"
