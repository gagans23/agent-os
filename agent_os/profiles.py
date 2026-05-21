"""
profiles — specialized agent profiles.

Each profile has its own allowed tools, memory namespace, personality, and a
default quality threshold for the eval gate. Profiles are configuration, not
code — the runner uses them to scope what an agent may do and how strictly it is
judged.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentProfile:
    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    personality: str = ""
    memory_namespace: str = "default"
    pass_threshold: float = 85.0  # NARI score below which the run is flagged


PROFILES: dict[str, AgentProfile] = {
    "researcher": AgentProfile(
        name="researcher",
        description="Browser research and summarization.",
        allowed_tools=["browser_open", "web_search", "save_artifact"],
        personality="Concise, evidence-first. Cites sources; keeps logs out of the answer.",
        memory_namespace="research",
        pass_threshold=85.0,
    ),
    "operator": AgentProfile(
        name="operator",
        description="Gmail, WhatsApp, and status checks.",
        allowed_tools=["gmail_list_unread", "send_whatsapp", "status_check"],
        personality="Careful with recipients and secrets. Confirms delivery; avoids duplicates.",
        memory_namespace="ops",
        pass_threshold=90.0,  # stricter — touches messaging + credentials
    ),
    "builder": AgentProfile(
        name="builder",
        description="Code changes, GitHub, and deployments.",
        allowed_tools=["edit_file", "run_tests", "git", "deploy"],
        personality="Test-driven. Small, reversible changes; never bypasses CI.",
        memory_namespace="build",
        pass_threshold=85.0,
    ),
    "qa": AgentProfile(
        name="qa",
        description="Ninja Harness evals, regression tests, red-team checks.",
        allowed_tools=["ninja_harness", "run_tests", "redteam"],
        personality="Skeptical. Looks for the failure the demo hides.",
        memory_namespace="qa",
        pass_threshold=80.0,
    ),
}


def get_profile(name: str) -> AgentProfile:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile {name!r}. Available: {sorted(PROFILES)}")
    return PROFILES[name]
