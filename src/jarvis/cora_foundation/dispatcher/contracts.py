"""DispatchRequest / DispatchResult — Dispatcher output (never adapter execution)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from ..conversation.contracts.schema import freeze_mapping

SCHEMA_FAMILY = "cora.dispatch.contracts"
SCHEMA_VERSION = 1
KIND_REQUEST = "DispatchRequest"
KIND_RESULT = "DispatchResult"


class ApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"


class DispatchExecutionMode(str, Enum):
    """v1: always none — Dispatcher prepares only; adapters run later."""

    NONE = "none"


class DispatchOutcome(str, Enum):
    READY = "ready"
    EMPTY = "empty"
    DENY = "deny"
    UNSUPPORTED_TOOL = "unsupported_tool"
    PARTIAL = "partial"


@dataclass(frozen=True)
class DispatchRequest:
    """Standard contract every adapter will receive later."""

    dispatch_id: str
    plan_id: str
    tool: str
    capability: str
    execution_mode: DispatchExecutionMode = DispatchExecutionMode.NONE
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    payload: Mapping[str, Any] = None  # type: ignore[assignment]
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]
    timestamp: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_mapping(self.payload))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.execution_mode, str):
            object.__setattr__(
                self, "execution_mode", DispatchExecutionMode(self.execution_mode)
            )
        if isinstance(self.approval_state, str):
            object.__setattr__(self, "approval_state", ApprovalState(self.approval_state))
        if not self.timestamp:
            object.__setattr__(
                self,
                "timestamp",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_REQUEST,
            "dispatch_id": self.dispatch_id,
            "plan_id": self.plan_id,
            "tool": self.tool,
            "capability": self.capability,
            "execution_mode": self.execution_mode.value,
            "approval_state": self.approval_state.value,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }

    @staticmethod
    def new_id() -> str:
        return f"disp_{uuid4().hex[:12]}"


@dataclass(frozen=True)
class DispatchResult:
    """Aggregate outcome of dispatching a ToolPlan (no adapter calls)."""

    result_id: str
    plan_id: str
    outcome: DispatchOutcome
    requests: tuple[DispatchRequest, ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.requests, list):
            object.__setattr__(self, "requests", tuple(self.requests))
        frozen_errors: list[Mapping[str, Any]] = []
        for err in self.errors or ():
            frozen_errors.append(freeze_mapping(dict(err)))
        object.__setattr__(self, "errors", tuple(frozen_errors))
        if isinstance(self.outcome, str):
            object.__setattr__(self, "outcome", DispatchOutcome(self.outcome))

    @property
    def empty(self) -> bool:
        return len(self.requests) == 0

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_RESULT,
            "result_id": self.result_id,
            "plan_id": self.plan_id,
            "outcome": self.outcome.value,
            "requests": [r.to_canonical_dict() for r in self.requests],
            "errors": [dict(e) for e in self.errors],
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def new_id() -> str:
        return f"dres_{uuid4().hex[:12]}"
