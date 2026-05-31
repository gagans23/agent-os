"""
agent-os — a self-improving agent platform that uses Ninja Harness as its
evaluation gate.

Pipeline:  command → profile → memory → skill → execute → trace → evaluate
           → propose improvement → report

This package provides the runtime spine. Live integrations (WhatsApp/Meta,
Gmail, Cloudflare Tunnel) are pluggable adapters you wire with your own
credentials — none are bundled or faked.
"""

__version__ = "0.17.0"

from agent_os.agent_memory import AgentMemory
from agent_os.approvals import ApprovalStore
from agent_os.audit import AuditLog
from agent_os.command_router import CommandRouter
from agent_os.context import ContextStore
from agent_os.hooks import (
    Hook,
    HookContext,
    HookPhase,
    HookRegistry,
    redact_secrets,
    redaction_hook,
)
from agent_os.improvement import ImprovementProposal, propose_improvement
from agent_os.insights import (
    CrossEpisodeSynthesizer,
    Digest,
    EpisodeSummary,
    Insight,
)
from agent_os.jobs import JobStore
from agent_os.onboarding import SetupResult, guidance, run_setup
from agent_os.orchestrator import Orchestrator, SubResult, SubTask, SwarmResult
from agent_os.profiles import PROFILES, AgentProfile, get_profile
from agent_os.providers import (
    AnthropicProvider,
    EchoProvider,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    ProviderError,
    config_path,
    configured_provider_spec,
    get_provider,
    provider_from_env,
    set_configured_provider,
)
from agent_os.reasoners import LLMReasoner
from agent_os.risk import RiskAssessment, RiskLevel, classify_risk
from agent_os.runner import JobResult, run_job
from agent_os.skill_registry import Skill, SkillRegistry
from agent_os.trace_recorder import JobRecorder, TraceRecorder

__all__ = [
    "AgentMemory",
    "AgentProfile",
    "AnthropicProvider",
    "ApprovalStore",
    "AuditLog",
    "CommandRouter",
    "ContextStore",
    "CrossEpisodeSynthesizer",
    "Digest",
    "EchoProvider",
    "EpisodeSummary",
    "Hook",
    "HookContext",
    "HookPhase",
    "HookRegistry",
    "ImprovementProposal",
    "Insight",
    "JobRecorder",
    "LLMReasoner",
    "JobResult",
    "JobStore",
    "OllamaProvider",
    "OpenAIProvider",
    "Orchestrator",
    "PROFILES",
    "Provider",
    "ProviderError",
    "RiskAssessment",
    "RiskLevel",
    "SetupResult",
    "Skill",
    "SkillRegistry",
    "SubResult",
    "SubTask",
    "SwarmResult",
    "TraceRecorder",
    "__version__",
    "classify_risk",
    "config_path",
    "configured_provider_spec",
    "get_profile",
    "get_provider",
    "guidance",
    "propose_improvement",
    "provider_from_env",
    "redact_secrets",
    "redaction_hook",
    "run_job",
    "run_setup",
    "set_configured_provider",
]
