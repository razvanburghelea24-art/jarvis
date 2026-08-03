"""AgentResult + QualityScores — agents return these and nothing else."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AgentRole(str, Enum):
    RESEARCH = "Research"
    CODE = "Code"
    REVIEW = "Review"
    VALIDATION = "Validation"


class AgentResultStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_MORE_CONTEXT = "NEEDS_MORE_CONTEXT"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class QualityScores:
    """Per-dimension quality — never a single blended 'decision'."""

    architecture: float = 0.0
    security: float = 0.0
    performance: float = 0.0
    complexity: float = 0.0
    maintainability: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "architecture", clamp01(self.architecture))
        object.__setattr__(self, "security", clamp01(self.security))
        object.__setattr__(self, "performance", clamp01(self.performance))
        object.__setattr__(self, "complexity", clamp01(self.complexity))
        object.__setattr__(self, "maintainability", clamp01(self.maintainability))

    def to_public_dict(self) -> dict[str, float]:
        return {
            "architecture": self.architecture,
            "security": self.security,
            "performance": self.performance,
            "complexity": self.complexity,
            "maintainability": self.maintainability,
        }


@dataclass(frozen=True)
class AgentResult:
    """
    Sole agent output. No side effects. No 'I did it' — 'task finished'.
    Dispatcher is never called from agents.
    """

    result_id: str
    agent_role: AgentRole
    task_id: str
    plan_id: str | None
    status: AgentResultStatus
    summary: str
    findings: tuple[str, ...] = ()
    artifacts: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    quality: QualityScores = field(default_factory=QualityScores)
    proposed_capabilities: tuple[str, ...] = ()
    recommends_review: bool = False
    created_at: str = field(default_factory=_now)
    dispatches: bool = False  # always False in Phase 5
    decides_architecture: bool = False  # always False
    final_decision: bool = False  # always False — Owner / Planner only

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", clamp01(self.confidence))
        object.__setattr__(self, "dispatches", False)
        object.__setattr__(self, "decides_architecture", False)
        object.__setattr__(self, "final_decision", False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "agent_role": self.agent_role.value,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "status": self.status.value,
            "summary": self.summary,
            "findings": list(self.findings),
            "artifacts": dict(self.artifacts),
            "confidence": self.confidence,
            "quality": self.quality.to_public_dict(),
            "proposed_capabilities": list(self.proposed_capabilities),
            "recommends_review": self.recommends_review,
            "created_at": self.created_at,
            "dispatches": False,
            "decides_architecture": False,
            "final_decision": False,
        }


def new_result_id() -> str:
    return f"ares_{uuid.uuid4().hex[:14]}"
