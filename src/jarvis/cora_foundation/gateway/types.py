"""Gateway types — structured command/intent/plan objects (no business logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    READ = "read"
    SAFE_LOCAL = "safe_local"
    OWNER_CONFIRM = "owner_confirm"
    CRITICAL = "critical"
    FORBIDDEN = "forbidden"


class SourceChannel(str, Enum):
    DISCORD = "discord"
    DESKTOP = "desktop"
    OVERLAY = "overlay"
    CLI = "cli"
    VOICE = "voice"
    API = "api"
    N8N = "n8n"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandEnvelope:
    """Raw input from any future channel — normalized later."""

    text: str
    source: SourceChannel = SourceChannel.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedCommand:
    text: str
    source: SourceChannel
    metadata: dict[str, Any]
    normalized_at: str


@dataclass(frozen=True)
class Intent:
    intent_id: str
    type: str
    confidence: float
    source: SourceChannel
    owner_id: str | None
    workspace_id: str | None
    session_id: str | None
    required_capabilities: tuple[str, ...]
    risk_level: RiskLevel
    estimated_cost: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "type": self.type,
            "confidence": self.confidence,
            "source": self.source.value,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "required_capabilities": list(self.required_capabilities),
            "risk_level": self.risk_level.value,
            "estimated_cost": self.estimated_cost,
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    intent_id: str
    capabilities: tuple[str, ...]
    risk_level: RiskLevel
    requires_approval: bool = False
    requires_confirmation: bool = False
    blocked_reason: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "capabilities": list(self.capabilities),
            "risk_level": self.risk_level.value,
            "requires_approval": self.requires_approval,
            "requires_confirmation": self.requires_confirmation,
            "blocked_reason": self.blocked_reason,
        }
