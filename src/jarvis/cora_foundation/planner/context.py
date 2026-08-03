"""Planner input context — observe only. No adapters, no writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlannerContext:
    """
    Allowed inputs only:
    Identity · Memory snapshot · Gateway request · Hub snapshots ·
    Policy context · Runtime state.
    """

    request_id: str
    request_text: str
    identity: dict[str, Any] = field(default_factory=dict)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)
    integration_snapshots: tuple[dict[str, Any], ...] = ()
    policy_context: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_text": self.request_text,
            "identity": dict(self.identity),
            "memory_snapshot": {
                "enabled": self.memory_snapshot.get("enabled"),
                "revision": self.memory_snapshot.get("revision"),
                "record_count": self.memory_snapshot.get("record_count"),
            },
            "integration_count": len(self.integration_snapshots),
            "policy_context": dict(self.policy_context),
            "runtime_state": dict(self.runtime_state),
            "source": self.source,
        }
