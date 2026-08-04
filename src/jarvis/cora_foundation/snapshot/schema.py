"""Unified Snapshot schema — one object, eight sections."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA = "cora.runtime.snapshot.v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SectionMeta:
    source: str  # live | bridge_stub | off
    health: str  # on | off | degraded
    health_pct: float  # 0..100
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedSnapshot:
    schema: str = SCHEMA
    generated_at: str = field(default_factory=_now)
    runtime: dict[str, Any] = field(default_factory=dict)
    planner: dict[str, Any] = field(default_factory=dict)
    scheduler: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    gateway: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    operator: dict[str, Any] = field(default_factory=dict)
    # Additive (Beta): ConversationState projection — never Persona/Avatar fields.
    conversation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "runtime": dict(self.runtime),
            "planner": dict(self.planner),
            "scheduler": dict(self.scheduler),
            "agents": dict(self.agents),
            "memory": dict(self.memory),
            "gateway": dict(self.gateway),
            "audit": dict(self.audit),
            "operator": dict(self.operator),
            "conversation": dict(self.conversation),
        }


def empty_snapshot() -> UnifiedSnapshot:
    stub = lambda name: {
        "source": "off",
        "health": "off",
        "health_pct": 0.0,
        "detail": f"{name} not collected",
        "status": "Idle",
    }
    conversation_off = {
        "source": "off",
        "health": "off",
        "health_pct": 0.0,
        "detail": "conversation state not projected",
        "status": "Idle",
        "schema_family": "cora.conversation.contracts",
        "schema_version": 1,
        "kind": "ConversationState",
        "presentation": "Idle",
        "lifecycle": "Idle",
        "session_id": None,
        "request_id": None,
        "workspace_id": None,
        "error_class": None,
    }
    return UnifiedSnapshot(
        runtime=stub("runtime"),
        planner=stub("planner"),
        scheduler=stub("scheduler"),
        agents=stub("agents"),
        memory=stub("memory"),
        gateway=stub("gateway"),
        audit=stub("audit"),
        operator={**stub("operator"), "indicator": "OBSERVE"},
        conversation=conversation_off,
    )


def bar10(pct: float) -> str:
    fill = max(0, min(10, int(round(float(pct) / 10.0))))
    return ("█" * fill) + ("░" * (10 - fill))
