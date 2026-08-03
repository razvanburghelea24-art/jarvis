"""Audit event types and record schema — data only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuditEventType(str, Enum):
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    REQUEST_NORMALIZED = "REQUEST_NORMALIZED"
    IDENTITY_RESOLVED = "IDENTITY_RESOLVED"
    MEMORY_RESOLVED = "MEMORY_RESOLVED"
    INTENT_CLASSIFIED = "INTENT_CLASSIFIED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    PLAN_CREATED = "PLAN_CREATED"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    DISPATCH_COMPLETED = "DISPATCH_COMPLETED"
    REQUEST_COMPLETED = "REQUEST_COMPLETED"
    REQUEST_FAILED = "REQUEST_FAILED"
    SAFE_MODE_BLOCK = "SAFE_MODE_BLOCK"
    ESTOP_BLOCK = "ESTOP_BLOCK"
    # Phase 1E
    ESTOP_TRIGGERED = "ESTOP_TRIGGERED"
    ESTOP_RELEASED = "ESTOP_RELEASED"
    SAFE_MODE_ENTERED = "SAFE_MODE_ENTERED"
    SAFE_MODE_EXITED = "SAFE_MODE_EXITED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: str
    session_id: str | None
    owner_id: str | None
    workspace_id: str | None
    request_id: str
    intent_id: str | None
    event_type: AuditEventType
    status: str
    source: str | None
    capability: str | None
    risk_level: str | None
    duration_ms: float | None
    result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "event_type": self.event_type.value,
            "status": self.status,
            "source": self.source,
            "capability": self.capability,
            "risk_level": self.risk_level,
            "duration_ms": self.duration_ms,
            "result": dict(self.result),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        return cls(
            event_id=str(data["event_id"]),
            timestamp=str(data.get("timestamp") or utc_now_iso()),
            session_id=data.get("session_id"),
            owner_id=data.get("owner_id"),
            workspace_id=data.get("workspace_id"),
            request_id=str(data["request_id"]),
            intent_id=data.get("intent_id"),
            event_type=AuditEventType(str(data["event_type"])),
            status=str(data.get("status") or ""),
            source=data.get("source"),
            capability=data.get("capability"),
            risk_level=data.get("risk_level"),
            duration_ms=data.get("duration_ms"),
            result=dict(data.get("result") or {}),
            metadata=dict(data.get("metadata") or {}),
        )
