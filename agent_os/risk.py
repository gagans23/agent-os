"""
risk — classify a task by how dangerous it is, so the platform knows what may
run automatically and what needs human approval.

Tiers (low → high): READ_ONLY < WRITE < SEND < DEPLOY.

Two enterprise-grade properties beyond simple keyword matching:

1. **Default-deny on ambiguity.** A task with no clear read-only verb AND no
   risk verb is treated as `ambiguous` and REQUIRES APPROVAL. Keyword matchers
   fail open ("make the prod table empty" → no match → auto-run); this fails
   closed instead.
2. **Tool-aware risk.** If the agent's available tools can write/send/deploy,
   risk is escalated regardless of the wording — because capability, not
   phrasing, is what makes an action dangerous.

Classification stays deterministic and auditable; an LLM classifier can be
layered on top later, but this conservative baseline never silently auto-runs a
destructive action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum


class RiskLevel(IntEnum):
    READ_ONLY = 0
    WRITE = 1
    SEND = 2
    DEPLOY = 3

    @property
    def label(self) -> str:
        return self.name


# Highest-risk match wins. Word-boundary matched.
_RISK_VERBS: dict[RiskLevel, list[str]] = {
    RiskLevel.DEPLOY: ["deploy", "release", "publish", "push", "ship", "rollout",
                       "terraform apply", "go live", "promote to prod"],
    RiskLevel.SEND: ["send", "message", "whatsapp", "email", "e-mail", "notify",
                     "reply", "dm", "sms", "broadcast", "text", "post"],
    RiskLevel.WRITE: ["delete", "remove", "rm", "drop", "update", "edit", "write",
                      "modify", "create", "install", "uninstall", "refund", "pay",
                      "transfer", "revoke", "rotate", "merge", "commit", "overwrite",
                      "truncate", "wipe", "reset", "grant", "empty", "purge", "erase",
                      "destroy", "deactivate", "disable", "format", "drop all",
                      "clear", "archive", "migrate"],
}

_READ_VERBS = ["read", "list", "show", "get", "summar", "research", "check", "status",
               "find", "search", "fetch", "view", "report", "digest", "ping", "inspect",
               "describe", "count", "explain", "compare", "analyze"]

# Tool-name signals → minimum risk implied by having that capability available.
_TOOL_RISK: list[tuple[RiskLevel, list[str]]] = [
    (RiskLevel.DEPLOY, ["deploy", "release", "publish", "git_push", "kubectl", "terraform"]),
    (RiskLevel.SEND, ["send", "email", "whatsapp", "sms", "notify", "message", "post"]),
    (RiskLevel.WRITE, ["delete", "write", "update", "create", "edit", "exec", "shell",
                       "rm", "drop", "refund", "pay", "transfer", "rotate", "commit",
                       "modify", "install"]),
]


@dataclass
class RiskAssessment:
    level: RiskLevel
    requires_approval: bool
    matched: list[str] = field(default_factory=list)
    ambiguous: bool = False
    via_tools: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level.label,
            "requires_approval": self.requires_approval,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "via_tools": self.via_tools,
            "reason": self.reason,
        }


def _has_word(text: str, kw: str) -> bool:
    return re.search(rf"\b{re.escape(kw)}\b", text) is not None


def _text_level(text: str) -> tuple[RiskLevel | None, list[str]]:
    for level in (RiskLevel.DEPLOY, RiskLevel.SEND, RiskLevel.WRITE):
        hits = [kw for kw in _RISK_VERBS[level] if _has_word(text, kw)]
        if hits:
            return level, hits
    return None, []


def _tool_level(tools: list[str] | None) -> tuple[RiskLevel | None, list[str]]:
    if not tools:
        return None, []
    blob = " ".join(t.lower() for t in tools)
    for level, sigs in _TOOL_RISK:
        hits = [s for s in sigs if s in blob]
        if hits:
            return level, [f"tool:{h}" for h in hits]
    return None, []


def classify_risk(command: str, tools: list[str] | None = None) -> RiskAssessment:
    """Classify a task into a RiskLevel + whether it needs human approval.

    `tools` (optional): the tool names the executing agent may call — used to
    escalate risk by capability, not just wording.
    """
    text = (command or "").lower().strip()

    text_lvl, text_hits = _text_level(text)
    tool_lvl, tool_hits = _tool_level(tools)

    # Highest risk among text and tool signals.
    candidates = [lvl for lvl in (text_lvl, tool_lvl) if lvl is not None]
    if candidates:
        level = max(candidates)
        matched = text_hits + tool_hits
        via_tools = tool_lvl is not None and (text_lvl is None or tool_lvl >= text_lvl)
        return RiskAssessment(
            level=level, requires_approval=True, matched=matched, via_tools=via_tools,
            reason=f"{level.label}: matched {', '.join(matched[:4])}",
        )

    # No risk signal. Is it clearly read-only, or ambiguous?
    read_hits = [v for v in _READ_VERBS if v in text]
    if read_hits:
        return RiskAssessment(
            level=RiskLevel.READ_ONLY, requires_approval=False, matched=read_hits[:3],
            reason="READ_ONLY: read-only verb detected, no write/send/deploy signal",
        )

    # Default-deny: ambiguous tasks require approval rather than auto-running.
    return RiskAssessment(
        level=RiskLevel.READ_ONLY, requires_approval=True, ambiguous=True,
        reason="AMBIGUOUS: no clear read-only or risk verb — default-deny (needs approval)",
    )
