#!/bin/bash
#
# agent-os — double-click to start (macOS).
#
# Keep this file inside the agent-os folder. The first run sets up a small local
# environment (a couple of minutes); every run after that just opens the web UI
# in your browser. You don't type anything — this window only shows progress.
#
# To stop agent-os, close this window.

# Move to the repo root (this launcher lives in launchers/).
cd "$(dirname "$0")/.." || exit 1
clear 2>/dev/null || true

echo "🤖  Starting agent-os…"
echo

if [ ! -x ".venv/bin/agent-os" ]; then
  echo "First run: setting up a local environment. This can take a couple of minutes…"
  echo
  if ! ./install.sh; then
    echo
    echo "Setup needs Python 3.11+ (and git)."
    echo "Opening the Python download page — install it, then double-click this again."
    open "https://www.python.org/downloads/" 2>/dev/null || true
    read -r -p "Press Return to close this window." _ || true
    exit 1
  fi
fi

echo
echo "Opening the web UI in your browser…   (close this window to stop agent-os)"
exec .venv/bin/agent-os ui "$@"
