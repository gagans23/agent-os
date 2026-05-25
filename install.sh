#!/usr/bin/env bash
#
# agent-os one-command installer (local-first, dependency-light).
#
#   curl -fsSL https://raw.githubusercontent.com/gagans23/agent-os/main/install.sh | bash
# or, from a clone:
#   ./install.sh
#
# It creates a local virtualenv (.venv), installs the Ninja Harness eval gate and
# agent-os into it, and prints how to launch the web UI. No sudo, no global state.
set -euo pipefail

REPO_URL="https://github.com/gagans23/agent-os.git"
NINJA_URL="ninja-harness @ git+https://github.com/gagans23/ninja-harness.git"
PYTHON="${PYTHON:-python3}"

say() { printf "\033[1;34m▸\033[0m %s\n" "$*"; }
die() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# 1. Python 3.11+ check.
command -v "$PYTHON" >/dev/null 2>&1 || die "python3 not found. Install Python 3.11+ first."
"$PYTHON" - <<'PY' || die "agent-os needs Python 3.11 or newer."
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
say "Using $("$PYTHON" --version)"

# 2. Get the source (clone if we're not already inside the repo).
if [ ! -f "pyproject.toml" ] || ! grep -q 'name = "agent-os"' pyproject.toml 2>/dev/null; then
  command -v git >/dev/null 2>&1 || die "git not found (needed to fetch agent-os)."
  say "Cloning agent-os…"
  git clone --depth 1 "$REPO_URL" agent-os
  cd agent-os
fi

# 3. Virtualenv + install.
say "Creating virtualenv (.venv)…"
"$PYTHON" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
say "Upgrading pip…"
pip install --quiet --upgrade pip
say "Installing the Ninja Harness eval gate…"
pip install --quiet "$NINJA_URL"
say "Installing agent-os…"
pip install --quiet -e .

# 4. Smoke test.
say "Verifying…"
agent-os cmd "/ping" >/dev/null && say "OK"

cat <<EOF

\033[1;32m✓ agent-os is installed.\033[0m

  Launch the web UI (opens in your browser):
      .venv/bin/agent-os ui

  Or use the command line:
      .venv/bin/agent-os cmd "/help"
      .venv/bin/agent-os cmd "/learn ~/notes.md"
      .venv/bin/agent-os cmd "/ask what did I learn?"

  Optional — plug in a local, free model (no API key):
      Install Ollama (https://ollama.com), then:
      export AGENT_OS_PROVIDER=ollama:llama3

EOF
