"""
risk — classify a task by how dangerous it is, so the platform knows what may
run automatically and what needs human approval.

Tiers (low → high):
    READ_ONLY  — read/list/summarize/research/status → runs automatically
    WRITE      — create/edit/delete/install/refund/rotate → needs approval
    SEND       — message/email/notify/post → needs approval
    DEPLOY     — deploy/release/publish/push/ship → needs approval

Classification is deterministic keyword matching on the task text — auditable and
testable. It is intentionally conservative: anything that isn't clearly read-only
should be reviewed. This is the gate behind Level 3 "controlled autonomy".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    READ_ONLY = 0
    WRITE = 1
    SEND = 2
    DEPLOY = 3

    @property
    def label(self) -> str:
        return self.name


# Highest-risk keyword wins. Ordered most → least dangerous.
_RULES: list[tuple[RiskLevel, list[str]]] = [
    (RiskLevel.DEPLOY, ["deploy", "release", "publish", "git push", "ship ", "rollout",
                        "terraform apply", "production", "go live"]),
    (RiskLevel.SEND, ["send", "message", "whatsapp", "email", "e-mail", "notify",
                      "reply", "dm ", "sms", "post to", "broadcast", "text "]),
    (RiskLevel.WRITE, ["delete", "remove", " rm ", "drop ", "update", "edit", "write",
                       "modify", "create", "install", "uninstall", "refund", "pay",
                       "transfer", "revoke", "rotate", "merge", "commit", "overwrite",
                       "truncate", "wipe", "reset", "grant", "approve"]),
]

_READ_HINTS = ["read", "list", "show", "get", "summar", "research", "check", "status",
               "find", "search", "fetch", "view", "report", "digest", "eval", "ping"]


@dataclass
class RiskAssessment:
    level: RiskLevel
    requires_approval: bool
    matched: list[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "level": self.level.label,
            "requires_approval": self.requires_approval,
            "matched": self.matched,
            "reason": self.reason,
        }


def _contains(text: str, keyword: str) -> bool:
    # Word-ish match: keyword may include spaces; use substring on a padded string.
    return keyword in f" {text} "


def classify_risk(command: str) -> RiskAssessment:
    """Classify a task/command into a RiskLevel + whether it needs approval."""
    text = (command or "").lower().strip()
    for level, keywords in _RULES:
        matched = [k.strip() for k in keywords if _contains(text, k) or re.search(rf"\b{re.escape(k.strip())}\b", text)]
        if matched:
            return RiskAssessment(
                level=level,
                requires_approval=True,
                matched=matched,
                reason=f"{level.label}: matched {', '.join(matched[:3])}",
            )
    read_match = [h for h in _READ_HINTS if h in text]
    reason = ("READ_ONLY: read-only verb detected" if read_match
              else "READ_ONLY: no write/send/deploy verbs detected")
    return RiskAssessment(RiskLevel.READ_ONLY, False, read_match[:3], reason)
