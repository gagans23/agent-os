"""
allowlist — sender authorization.

The platform must only act on commands from authorized senders (e.g. your own
WhatsApp number). This is a small, well-tested gate used by the gateway before a
command is routed. Entries can be loaded from a file (one per line) or a list;
phone numbers are normalized so formatting differences don't cause false denials.

This is the *mechanism*. Wiring it to your real WhatsApp sender id happens in the
gateway (Level 3); the allowlist itself is reliability/security infrastructure.
"""

from __future__ import annotations

import re
from pathlib import Path

_DIGITS = re.compile(r"[^\d+]")


def normalize_sender(sender: str) -> str:
    """Normalize a sender id. Phone-like ids keep a leading + and digits only;
    other ids (usernames) are lowercased and stripped."""
    s = (sender or "").strip()
    if not s:
        return ""
    if any(ch.isdigit() for ch in s) and not s[0].isalpha():
        cleaned = _DIGITS.sub("", s)
        # collapse a leading 00 to + and keep a single leading +
        if cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]
        return cleaned
    return s.lower()


class Allowlist:
    """An allowlist of authorized senders."""

    def __init__(self, entries: list[str] | None = None, path: str | Path | None = None) -> None:
        self._entries: set[str] = set()
        for e in entries or []:
            self.add(e)
        if path:
            self.load(path)

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self.add(line)

    def add(self, sender: str) -> None:
        norm = normalize_sender(sender)
        if norm:
            self._entries.add(norm)

    def remove(self, sender: str) -> None:
        self._entries.discard(normalize_sender(sender))

    def is_allowed(self, sender: str) -> bool:
        if not self._entries:
            return False  # fail closed: empty allowlist denies everyone
        return normalize_sender(sender) in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> list[str]:
        return sorted(self._entries)
