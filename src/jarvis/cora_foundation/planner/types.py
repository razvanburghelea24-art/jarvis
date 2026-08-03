"""Plan artifact — standardized Planner output. Never executed here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class PlanKind(str, Enum):
    ANALYSIS = "Analysis"
    DIAGNOSIS = "Diagnosis"
    IMPLEMENTATION = "Implementation"
    REVIEW = "Review"
    MIGRATION = "Migration"
    CLEANUP = "Cleanup"
    RESEARCH = "Research"
    RELEASE = "Release"
    ROLLBACK = "Rollback"


class PlanRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    title: str
    capability: str | None = None
    depends_on: tuple[str, ...] = ()
    notes: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "capability": self.capability,
            "depends_on": list(self.depends_on),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Plan:
    """Standard Planner output — thinking only, no side effects."""

    plan_id: str
    goal: str
    summary: str
    kind: PlanKind
    steps: tuple[PlanStep, ...]
    dependencies: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    risk_level: PlanRiskLevel
    risk_reason: str
    estimated_cost: float
    estimated_duration_s: float
    requires_owner_approval: bool
    status: PlanStatus
    request_id: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    executable: bool = False  # always False in Phase 4

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "summary": self.summary,
            "kind": self.kind.value,
            "steps": [s.to_public_dict() for s in self.steps],
            "dependencies": list(self.dependencies),
            "required_capabilities": list(self.required_capabilities),
            "risk_level": self.risk_level.value,
            "risk_reason": self.risk_reason,
            "estimated_cost": self.estimated_cost,
            "estimated_duration": self.estimated_duration_s,
            "requires_owner_approval": self.requires_owner_approval,
            "status": self.status.value,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "executable": False,
        }
