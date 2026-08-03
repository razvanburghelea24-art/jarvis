"""Policy Engine — authorization decisions only. No Discord/Overlay/GitHub knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Intent, RiskLevel


class PolicyDecisionKind(str, Enum):
    ALLOWED = "Allowed"
    DENIED = "Denied"
    NEEDS_APPROVAL = "Needs Approval"
    NEEDS_CONFIRMATION = "Needs Confirmation"
    BLOCKED_SAFE_MODE = "Blocked by Safe Mode"
    BLOCKED_E_STOP = "Blocked by E-Stop"


@dataclass(frozen=True)
class PolicyDecision:
    kind: PolicyDecisionKind
    reason: str = ""

    @property
    def may_dispatch(self) -> bool:
        return self.kind == PolicyDecisionKind.ALLOWED


class PolicyEngine:
    """Answers only with PolicyDecisionKind. Knows risk + runtime flags, not channels."""

    def evaluate(
        self,
        intent: Intent,
        *,
        safe_mode: bool = False,
        e_stop: bool = False,
        identity_enabled: bool = False,
        has_owner: bool = False,
    ) -> PolicyDecision:
        if e_stop:
            # E-Stop blocks external effects; diagnostic READ may continue.
            if intent.risk_level != RiskLevel.READ:
                return PolicyDecision(PolicyDecisionKind.BLOCKED_E_STOP, "e-stop active")
        if safe_mode and intent.risk_level in {RiskLevel.OWNER_CONFIRM, RiskLevel.CRITICAL, RiskLevel.FORBIDDEN}:
            return PolicyDecision(PolicyDecisionKind.BLOCKED_SAFE_MODE, "safe mode blocks elevated risk")

        if intent.risk_level == RiskLevel.FORBIDDEN:
            return PolicyDecision(PolicyDecisionKind.DENIED, "forbidden risk level")

        if intent.type == "unknown":
            return PolicyDecision(PolicyDecisionKind.DENIED, "unknown intent")

        if intent.type == "noop.empty":
            return PolicyDecision(PolicyDecisionKind.DENIED, "empty command")

        # Identity required for non-read when identity subsystem is on.
        if identity_enabled and not has_owner and intent.risk_level != RiskLevel.READ:
            return PolicyDecision(PolicyDecisionKind.DENIED, "owner identity required")

        if intent.risk_level == RiskLevel.CRITICAL:
            return PolicyDecision(PolicyDecisionKind.NEEDS_APPROVAL, "critical capability")

        if intent.risk_level == RiskLevel.OWNER_CONFIRM:
            return PolicyDecision(PolicyDecisionKind.NEEDS_CONFIRMATION, "owner confirmation required")

        # READ / SAFE_LOCAL
        return PolicyDecision(PolicyDecisionKind.ALLOWED, "within policy")
