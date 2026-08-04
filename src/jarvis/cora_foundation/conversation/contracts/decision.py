"""ConversationDecision — Planner-backed turn decision (v1 frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .schema import KIND_DECISION, envelope, freeze_mapping


class DecisionKind(str, Enum):
    ANSWER = "answer"
    TOOL = "tool"
    CLARIFY = "clarify"
    SWITCH_WORKSPACE = "switch_workspace"
    REFUSE = "refuse"


@dataclass(frozen=True)
class ConversationDecision:
    decision_id: str
    request_id: str
    kind: DecisionKind
    workspace_id: str
    planner_ref: str | None = None
    tool_intent: Mapping[str, Any] = None  # type: ignore[assignment]
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_intent", freeze_mapping(self.tool_intent))
        if isinstance(self.kind, str):
            object.__setattr__(self, "kind", DecisionKind(self.kind))

    def to_canonical_dict(self) -> dict[str, Any]:
        return envelope(
            kind=KIND_DECISION,
            payload={
                "decision_id": self.decision_id,
                "request_id": self.request_id,
                "decision_kind": self.kind.value,
                "workspace_id": self.workspace_id,
                "planner_ref": self.planner_ref,
                "tool_intent": dict(self.tool_intent),
                "reason": self.reason,
            },
        )
