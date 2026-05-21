"""
token_health — check configured secrets without ever exposing them.

Verifies that required tokens are present (in the environment), have a plausible
shape, and optionally aren't past a recorded expiry. It NEVER logs or returns the
token value. Live validation (e.g. calling the Meta Graph API to confirm a
WhatsApp token still works) is a pluggable hook you supply — there is no bundled
or faked API call here.

    statuses = check_tokens(["WHATSAPP_TOKEN", "META_APP_SECRET"])
    # or with live validation you control:
    statuses = check_tokens(["WHATSAPP_TOKEN"], validator=my_meta_check)
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# validator(name, value) -> (ok, detail). Receives the secret value; must not log it.
Validator = Callable[[str, str], "tuple[bool, str]"]


@dataclass
class TokenStatus:
    name: str
    present: bool
    shape_ok: bool
    expires_at: str | None = None
    expired: bool | None = None
    valid: bool | None = None  # None = not live-validated
    detail: str = ""

    @property
    def healthy(self) -> bool:
        if not self.present or not self.shape_ok:
            return False
        if self.expired:
            return False
        if self.valid is False:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def _load_expiry(name: str, expiry_file: str | Path | None) -> str | None:
    if not expiry_file:
        return None
    p = Path(expiry_file)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data.get(name)
    except Exception:  # noqa: BLE001
        return None


def check_tokens(required: list[str], *, validator: Validator | None = None,
                 min_len: int = 16, expiry_file: str | Path | None = None) -> list[TokenStatus]:
    """Check each required token by env-var name. Values are never returned/logged."""
    results: list[TokenStatus] = []
    now = datetime.now(UTC)
    for name in required:
        value = os.environ.get(name, "")
        present = bool(value)
        shape_ok = present and len(value) >= min_len
        expires_at = _load_expiry(name, expiry_file)
        expired: bool | None = None
        if expires_at:
            try:
                expired = datetime.fromisoformat(expires_at) <= now
            except ValueError:
                expired = None
        valid: bool | None = None
        detail = "ok"
        if not present:
            detail = "missing from environment"
        elif not shape_ok:
            detail = f"too short (<{min_len} chars)"
        elif expired:
            detail = f"expired at {expires_at}"
        elif validator is not None:
            try:
                valid, detail = validator(name, value)
            except Exception as exc:  # noqa: BLE001
                valid, detail = False, f"validator error: {type(exc).__name__}"
        results.append(TokenStatus(name=name, present=present, shape_ok=shape_ok,
                                   expires_at=expires_at, expired=expired,
                                   valid=valid, detail=detail))
    return results


def render(statuses: list[TokenStatus]) -> str:
    lines = ["Token health:"]
    for s in statuses:
        mark = "ok " if s.healthy else "FAIL"
        live = "" if s.valid is None else (" validated" if s.valid else " INVALID")
        lines.append(f"  [{mark}] {s.name}: {s.detail}{live}")
    return "\n".join(lines)
