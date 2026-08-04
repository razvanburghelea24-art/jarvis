"""PlannerDecision — sole output of Planner Routing (orchestrate only, never execute)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from ..conversation.contracts.schema import freeze_mapping

SCHEMA_FAMILY = "cora.planner.routing.contracts"
SCHEMA_VERSION = 1
KIND_DECISION = "PlannerDecision"


class PlannerRoute(str, Enum):
    DIRECT_RESPONSE = "DirectResponse"
    EXISTING_PLAN = "ExistingPlan"
    CREATE_PLAN = "CreatePlan"


class PlannerRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PlannerDecision:
    """Whether a plan is needed — never an executable TaskGraph."""

    decision_id: str
    request_id: str
    required: bool
    reason: str
    route: PlannerRoute
    priority: int = 5  # 1 high … 10 low
    estimated_steps: int = 0
    estimated_duration_sec: float = 0.0
    estimated_cost: float = 0.0
    risk: PlannerRisk = PlannerRisk.NONE
    required_capabilities: tuple[str, ...] = ()
    approval_required: bool = False
    planner_mode: str = "deterministic_v1"
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.route, str):
            object.__setattr__(self, "route", PlannerRoute(self.route))
        if isinstance(self.risk, str):
            object.__setattr__(self, "risk", PlannerRisk(self.risk))
        if isinstance(self.required_capabilities, list):
            object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))
        object.__setattr__(self, "priority", max(1, min(10, int(self.priority))))
        object.__setattr__(self, "estimated_steps", max(0, int(self.estimated_steps)))
        object.__setattr__(self, "estimated_duration_sec", float(self.estimated_duration_sec))
        object.__setattr__(self, "estimated_cost", float(self.estimated_cost))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_DECISION,
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "required": self.required,
            "reason": self.reason,
            "route": self.route.value,
            "priority": self.priority,
            "estimated_steps": self.estimated_steps,
            "estimated_duration": self.estimated_duration_sec,
            "estimated_cost": self.estimated_cost,
            "risk": self.risk.value,
            "required_capabilities": list(self.required_capabilities),
            "approval_required": self.approval_required,
            "planner_mode": self.planner_mode,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def new_id() -> str:
        return f"pdec_{uuid4().hex[:12]}"
