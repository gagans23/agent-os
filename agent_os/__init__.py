"""
agent-os — a self-improving agent platform that uses Ninja Harness as its
evaluation gate.

Pipeline:  command → profile → memory → skill → execute → trace → evaluate
           → propose improvement → report

This package provides the runtime spine. Live integrations (WhatsApp/Meta,
Gmail, Cloudflare Tunnel) are pluggable adapters you wire with your own
credentials — none are bundled or faked.
"""

__version__ = "0.1.0"

from agent_os.agent_memory import AgentMemory
from agent_os.command_router import CommandRouter
from agent_os.improvement import ImprovementProposal, propose_improvement
from agent_os.jobs import JobStore
from agent_os.profiles import PROFILES, AgentProfile, get_profile
from agent_os.runner import JobResult, run_job
from agent_os.skill_registry import Skill, SkillRegistry
from agent_os.trace_recorder import JobRecorder, TraceRecorder

__all__ = [
    "AgentMemory",
    "AgentProfile",
    "CommandRouter",
    "ImprovementProposal",
    "JobRecorder",
    "JobResult",
    "JobStore",
    "PROFILES",
    "Skill",
    "SkillRegistry",
    "TraceRecorder",
    "__version__",
    "get_profile",
    "propose_improvement",
    "run_job",
]
