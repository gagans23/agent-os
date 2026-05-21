"""
agent-os — a self-improving agent platform that uses Ninja Harness as its
evaluation gate.

Pipeline:  command → profile → memory → skill → execute → trace → evaluate
           → propose improvement → report

This package provides the runtime spine. Live integrations (WhatsApp/Meta,
Gmail, Cloudflare Tunnel) are pluggable adapters you wire with your own
credentials — none are bundled or faked.
"""

from agent_os.agent_memory import AgentMemory
from agent_os.improvement import ImprovementProposal, propose_improvement
from agent_os.profiles import PROFILES, AgentProfile, get_profile
from agent_os.runner import JobResult, run_job
from agent_os.skill_registry import Skill, SkillRegistry
from agent_os.trace_recorder import JobRecorder, TraceRecorder

__version__ = "0.1.0"

__all__ = [
    "AgentMemory",
    "AgentProfile",
    "ImprovementProposal",
    "JobRecorder",
    "JobResult",
    "PROFILES",
    "Skill",
    "SkillRegistry",
    "TraceRecorder",
    "__version__",
    "get_profile",
    "propose_improvement",
    "run_job",
]
