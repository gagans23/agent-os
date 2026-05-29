"""
hooks — composable before/after-action hooks for the job loop.

A hook is a small callable that runs around every job, so you can layer in
cross-cutting behavior (redaction, logging, custom metering, allow/deny
enrichment) **without forking the runner**. This is the composability seam:
agent-os ships the governed loop; you compose extra policy on top of it.

Two phases:

    BEFORE  — fires after context is assembled, before the agent runs.
              May rewrite the context the agent sees (e.g. strip secrets that
              leaked into memory before they reach the model).
    AFTER   — fires after the agent returns, before the output is traced/scored.
              May rewrite the final output (e.g. redact secrets the agent
              produced before they're persisted or sent).

Hooks are pure-Python, in-process, and synchronous — no new dependency. They
never bypass the risk gate, the audit log, or the eval gate; they run *inside*
the governed loop, around the agent call.

Built-in: `redaction_hook()` masks common secrets (API keys, bearer tokens,
emails) in both context and output. It's wired on by default in the runner so
nothing privileged leaks through the loop unredacted.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class HookPhase(StrEnum):
    BEFORE = "before"
    AFTER = "after"


@dataclass
class HookContext:
    """What a hook sees and may modify. Mutate `context` (before) or `output`
    (after) in place; the runner reads them back after each phase."""

    phase: HookPhase
    command: str
    profile: str
    job_id: str
    context: str = ""           # memory + skill context the agent will see
    output: str | None = None   # the agent's final answer (AFTER phase only)
    meta: dict = field(default_factory=dict)


# A hook: given the context, optionally mutate it in place. Return value ignored.
Hook = Callable[[HookContext], None]


class HookRegistry:
    """An ordered set of before/after hooks. Register your own, or start from
    `HookRegistry.default()` which includes redaction.

    Hooks run in registration order. A failing hook is isolated: its exception
    is swallowed (and noted in `ctx.meta['hook_errors']`) so one bad hook can't
    break the job — the governed loop must keep running.
    """

    def __init__(self) -> None:
        self._before: list[tuple[str, Hook]] = []
        self._after: list[tuple[str, Hook]] = []

    # --- registration ------------------------------------------------------

    def add_before(self, hook: Hook, *, name: str | None = None) -> HookRegistry:
        self._before.append((name or getattr(hook, "__name__", "hook"), hook))
        return self

    def add_after(self, hook: Hook, *, name: str | None = None) -> HookRegistry:
        self._after.append((name or getattr(hook, "__name__", "hook"), hook))
        return self

    def add(self, hook: Hook, *, name: str | None = None) -> HookRegistry:
        """Register a hook for both phases (it can branch on `ctx.phase`)."""
        self.add_before(hook, name=name)
        self.add_after(hook, name=name)
        return self

    @property
    def names(self) -> dict[str, list[str]]:
        return {
            "before": [n for n, _ in self._before],
            "after": [n for n, _ in self._after],
        }

    # --- execution ---------------------------------------------------------

    def run_before(self, ctx: HookContext) -> HookContext:
        return self._run(self._before, ctx)

    def run_after(self, ctx: HookContext) -> HookContext:
        return self._run(self._after, ctx)

    @staticmethod
    def _run(hooks: list[tuple[str, Hook]], ctx: HookContext) -> HookContext:
        for name, hook in hooks:
            try:
                hook(ctx)
            except Exception as exc:  # noqa: BLE001 - one bad hook can't break the loop
                ctx.meta.setdefault("hook_errors", []).append(f"{name}: {type(exc).__name__}: {exc}")
        return ctx

    @classmethod
    def default(cls) -> HookRegistry:
        """The default registry: redaction on both phases. Compose more on top."""
        reg = cls()
        reg.add(redaction_hook(), name="redaction")
        return reg


# --- built-in hooks --------------------------------------------------------

# Common secret shapes. Conservative on purpose: prefer leaving a real value
# masked over leaking it. Patterns match the value; we replace with a marker.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Mask common secrets in `text`. Returns (redacted_text, kinds_found)."""
    if not text:
        return text, []
    found: list[str] = []
    out = text
    for kind, pat in _SECRET_PATTERNS:
        if pat.search(out):
            found.append(kind)
            out = pat.sub(f"[REDACTED:{kind}]", out)
    return out, found


def redaction_hook() -> Hook:
    """A hook that strips secrets from context (BEFORE) and output (AFTER).

    Defense-in-depth: secrets that leaked into memory never reach the model, and
    secrets the model emits never reach the trace, the eval gate, or a transport.
    """

    def _hook(ctx: HookContext) -> None:
        if ctx.phase is HookPhase.BEFORE and ctx.context:
            ctx.context, found = redact_secrets(ctx.context)
            if found:
                ctx.meta.setdefault("redacted", {}).setdefault("context", []).extend(found)
        elif ctx.phase is HookPhase.AFTER and ctx.output:
            ctx.output, found = redact_secrets(ctx.output)
            if found:
                ctx.meta.setdefault("redacted", {}).setdefault("output", []).extend(found)

    return _hook
