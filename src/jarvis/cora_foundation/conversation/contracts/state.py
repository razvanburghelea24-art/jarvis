"""ConversationState — lifecycle + presentation hint for Snapshot (v1 frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .schema import KIND_STATE, envelope


class LifecyclePhase(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    STREAMING = "Streaming"
    INTERRUPTED = "Interrupted"
    RESUME = "Resume"
    COMPLETED = "Completed"


class PresentationHint(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    PLANNING = "Planning"
    SPEAKING = "Speaking"
    SUCCESS = "Success"
    WAITING = "Waiting"
    WAITING_OWNER = "WaitingOwner"
    COMPLETED = "Completed"


class ErrorClass(str, Enum):
    TOOL_TIMEOUT = "tool_timeout"
    PLANNER_TIMEOUT = "planner_timeout"
    LLM_TIMEOUT = "llm_timeout"
    WORKSPACE_MISSING = "workspace_missing"
    MEMORY_UNAVAILABLE = "memory_unavailable"
    OPERATOR_UNAVAILABLE = "operator_unavailable"


@dataclass(frozen=True)
class ConversationState:
    session_id: str
    request_id: str | None
    workspace_id: str
    lifecycle: LifecyclePhase
    presentation: PresentationHint
    error_class: ErrorClass | None = None

    def __post_init__(self) -> None:
        if isinstance(self.lifecycle, str):
            object.__setattr__(self, "lifecycle", LifecyclePhase(self.lifecycle))
        if isinstance(self.presentation, str):
            object.__setattr__(self, "presentation", PresentationHint(self.presentation))
        if isinstance(self.error_class, str):
            object.__setattr__(self, "error_class", ErrorClass(self.error_class))

    def to_canonical_dict(self) -> dict[str, Any]:
        return envelope(
            kind=KIND_STATE,
            payload={
                "session_id": self.session_id,
                "request_id": self.request_id,
                "workspace_id": self.workspace_id,
                "lifecycle": self.lifecycle.value,
                "presentation": self.presentation.value,
                "error_class": self.error_class.value if self.error_class else None,
            },
        )
