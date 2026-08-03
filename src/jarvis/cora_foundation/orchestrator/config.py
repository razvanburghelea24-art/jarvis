"""Orchestrator configuration — confidence gates, retries, resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..agents.types import AgentRole


class ResourceHint(str, Enum):
    """Model/resource routing — agents never see provider choice logic."""

    DEEP_MODEL = "deep_model"
    FAST_MODEL = "fast_model"
    LOCAL_MODEL = "local_model"
    DEFAULT = "default"


@dataclass(frozen=True)
class OrchestratorConfig:
    """Configurable thresholds — not hard-coded forever."""

    # Role → minimum confidence of *upstream completed* deps to proceed
    confidence_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            AgentRole.RESEARCH.value: 0.0,
            AgentRole.CODE.value: 0.50,  # need research/prior >= 0.50
            AgentRole.REVIEW.value: 0.0,
            AgentRole.VALIDATION.value: 0.45,
        }
    )
    default_max_retry: int = 2
    default_backoff_s: float = 1.0
    backoff_multiplier: float = 2.0
    # Roles that pause for Owner Approval before RUNNING
    approval_roles: tuple[str, ...] = (AgentRole.CODE.value,)
    # Capability names that always require Owner Approval before RUNNING
    approval_capabilities: tuple[str, ...] = (
        "GitHub.create_pr",
        "Railway.deploy",
        "Server.restart",
        "Discord.send",
    )
    resource_by_role: dict[str, ResourceHint] = field(
        default_factory=lambda: {
            AgentRole.RESEARCH.value: ResourceHint.DEEP_MODEL,
            AgentRole.CODE.value: ResourceHint.FAST_MODEL,
            AgentRole.REVIEW.value: ResourceHint.DEEP_MODEL,
            AgentRole.VALIDATION.value: ResourceHint.FAST_MODEL,
        }
    )

    def threshold_for(self, role: AgentRole | str) -> float:
        key = role.value if isinstance(role, AgentRole) else str(role)
        return float(self.confidence_thresholds.get(key, 0.0))

    def resource_for(self, role: AgentRole | str) -> ResourceHint:
        key = role.value if isinstance(role, AgentRole) else str(role)
        return self.resource_by_role.get(key, ResourceHint.DEFAULT)
