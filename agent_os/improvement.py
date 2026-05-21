"""
improvement — propose-only self-improvement from evaluation results.

After a weak run (NARI score below the profile threshold), this turns the Ninja
Harness evaluation into a structured improvement *proposal*: the failure reason,
a suggested memory update, and a suggested skill patch.

IMPORTANT: proposals are never applied automatically. They require explicit human
approval (`proposal.approved = True` + your own apply step). The agent does not
rewrite itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImprovementProposal:
    job_id: str
    score: float
    threshold: float
    reasons: list[str] = field(default_factory=list)
    memory_suggestion: str = ""
    skill_patch_suggestion: str = ""
    skill_name: str | None = None
    approved: bool = False  # must be set True by a human before applying

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "score": self.score,
            "threshold": self.threshold,
            "reasons": self.reasons,
            "memory_suggestion": self.memory_suggestion,
            "skill_patch_suggestion": self.skill_patch_suggestion,
            "skill_name": self.skill_name,
            "approved": self.approved,
            "requires_human_approval": True,
        }


def propose_improvement(result: Any, *, job_id: str = "", threshold: float = 85.0,
                        skill_name: str | None = None) -> ImprovementProposal | None:
    """
    Build an improvement proposal from a Ninja Harness EvaluationResult.

    Returns None if the run is at/above threshold (nothing to propose).
    """
    score = float(getattr(result, "ninja_score", 0.0))
    if score >= threshold:
        return None

    # Gather the weakest applicable metrics and their guidance.
    weak: list[tuple[str, float]] = []
    recs: list[str] = []
    for m in getattr(result, "metric_results", []):
        if getattr(m, "is_applicable", True) and not m.passed:
            weak.append((m.name, m.score))
            recs.extend(getattr(m, "recommendations", []) or [])

    weak.sort(key=lambda x: x[1])
    reasons = list(getattr(result, "top_failure_reasons", []) or [])
    if not reasons and weak:
        reasons = [f"{name} scored {sc:.2f}" for name, sc in weak[:3]]

    worst_metric = weak[0][0] if weak else "overall"
    memory_suggestion = (
        f"Run {job_id or result.run_id} scored {score:.1f} (< {threshold:.0f}). "
        f"Weakest metric: {worst_metric}. Record this so future runs avoid the same gap: "
        + (reasons[0] if reasons else "review the trajectory.")
    )
    skill_patch_suggestion = (
        f"Add a 'Pitfalls' note to the matched skill about '{worst_metric}'. "
        + (recs[0] if recs else "Tighten the procedure to address the failure above.")
    )

    return ImprovementProposal(
        job_id=job_id or getattr(result, "run_id", ""),
        score=score,
        threshold=threshold,
        reasons=reasons[:3],
        memory_suggestion=memory_suggestion,
        skill_patch_suggestion=skill_patch_suggestion,
        skill_name=skill_name,
    )
