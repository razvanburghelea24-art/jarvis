"""ToolPlan — sole output of Tool Routing (never execution)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from ..conversation.contracts.schema import freeze_mapping

SCHEMA_FAMILY = "cora.tool.routing.contracts"
SCHEMA_VERSION = 1
KIND_PLAN = "ToolPlan"


class ToolRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(str, Enum):
    NONE = "none"
    SIMULATE = "simulate"
    DISPATCH = "dispatch"  # later — never executed here


@dataclass(frozen=True)
class ToolPlan:
    """Capabilities/tools required for a PlannerDecision — Dispatcher consumes later."""

    plan_id: str
    request_id: str
    planner_decision_id: str
    required_tools: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    approval_required: bool = False
    execution_mode: ExecutionMode = ExecutionMode.NONE
    estimated_cost: float = 0.0
    estimated_duration_sec: float = 0.0
    risk: ToolRisk = ToolRisk.NONE
    fallback_tools: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        for name in ("required_tools", "required_capabilities", "fallback_tools"):
            val = getattr(self, name)
            if isinstance(val, list):
                object.__setattr__(self, name, tuple(val))
        if isinstance(self.risk, str):
            object.__setattr__(self, "risk", ToolRisk(self.risk))
        if isinstance(self.execution_mode, str):
            object.__setattr__(self, "execution_mode", ExecutionMode(self.execution_mode))
        object.__setattr__(self, "estimated_cost", float(self.estimated_cost))
        object.__setattr__(self, "estimated_duration_sec", float(self.estimated_duration_sec))

    @property
    def empty(self) -> bool:
        return len(self.required_tools) == 0

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_PLAN,
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "planner_decision_id": self.planner_decision_id,
            "required_tools": list(self.required_tools),
            "required_capabilities": list(self.required_capabilities),
            "approval_required": self.approval_required,
            "execution_mode": self.execution_mode.value,
            "estimated_cost": self.estimated_cost,
            "estimated_duration": self.estimated_duration_sec,
            "risk": self.risk.value,
            "fallback_tools": list(self.fallback_tools),
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def new_id() -> str:
        return f"tplan_{uuid4().hex[:12]}"
