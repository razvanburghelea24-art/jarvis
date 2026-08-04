"""GatewayDecision — sole output of Live Execution Gateway (never executes)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from ..conversation.contracts.schema import freeze_mapping
from ..dispatcher.contracts import ApprovalState

SCHEMA_FAMILY = "cora.live.gateway.contracts"
SCHEMA_VERSION = 1
KIND_DECISION = "GatewayDecision"


class GatewayVerdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class ExecutionMode(str, Enum):
    DRY_RUN = "DryRun"
    LIVE = "Live"


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class GatewayDecision:
    """ALLOW | DENY only — adapters run only on ALLOW (outside this module)."""

    decision: GatewayVerdict
    reason: str
    mode: ExecutionMode
    approval_state: ApprovalState
    checks: tuple[CheckResult, ...] = ()
    timestamp: str = ""
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]
    decision_id: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.checks, list):
            object.__setattr__(self, "checks", tuple(self.checks))
        if isinstance(self.decision, str):
            object.__setattr__(self, "decision", GatewayVerdict(self.decision))
        if isinstance(self.mode, str):
            object.__setattr__(self, "mode", ExecutionMode(self.mode))
        if isinstance(self.approval_state, str):
            object.__setattr__(self, "approval_state", ApprovalState(self.approval_state))
        if not self.timestamp:
            object.__setattr__(
                self,
                "timestamp",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
        if not self.decision_id:
            object.__setattr__(self, "decision_id", f"gdec_{uuid4().hex[:12]}")

    @property
    def allowed(self) -> bool:
        return self.decision == GatewayVerdict.ALLOW

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_DECISION,
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "mode": self.mode.value,
            "approval_state": self.approval_state.value,
            "checks": [c.to_canonical_dict() for c in self.checks],
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }
