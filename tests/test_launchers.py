"""Integrity checks for the no-terminal launchers.

These are static/offline checks — they never run a launcher. They guard against
the regressions that actually broke double-click in the field: a missing
executable bit, a malformed ``Info.plist``, or the macOS ``.app`` wrapper losing
its link to the ``.command`` it drives.
"""

import plistlib
import stat
from pathlib import Path

LAUNCHERS = Path(__file__).resolve().parent.parent / "launchers"

MACOS_COMMAND = LAUNCHERS / "agent-os-macos.command"
LINUX_SH = LAUNCHERS / "agent-os-linux.sh"
WINDOWS_BAT = LAUNCHERS / "agent-os-windows.bat"
APP = LAUNCHERS / "agent-os.app"
APP_PLIST = APP / "Contents" / "Info.plist"
APP_EXE = APP / "Contents" / "MacOS" / "agent-os"


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def test_launchers_present():
    for path in (MACOS_COMMAND, LINUX_SH, WINDOWS_BAT, APP_PLIST, APP_EXE):
        assert path.exists(), f"missing launcher artifact: {path}"


def test_shell_launchers_are_executable():
    # The exec bit is what makes a double-click run rather than open in an editor.
    assert _is_executable(MACOS_COMMAND)
    assert _is_executable(LINUX_SH)
    assert _is_executable(APP_EXE)


def test_app_bundle_is_a_valid_app():
    with APP_PLIST.open("rb") as fh:
        info = plistlib.load(fh)
    assert info["CFBundlePackageType"] == "APPL"
    # CFBundleExecutable must name the file that actually exists in MacOS/.
    assert info["CFBundleExecutable"] == APP_EXE.name
    assert info["CFBundleIdentifier"]
    assert info["CFBundleShortVersionString"]


def test_app_executable_drives_the_command():
    # The .app is intentionally a thin wrapper: it must hand off to the visible
    # .command launcher (so users see first-run progress), not reimplement it.
    body = APP_EXE.read_text()
    assert body.startswith("#!")
    assert "agent-os-macos.command" in body
    assert "open" in body  # uses `open -a Terminal` to dodge the broken assoc.
