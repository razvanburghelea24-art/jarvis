"""Conversation Memory types — current session turns only.

Not Workspace Memory. Not Core Memory. Not Audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from ..contracts.schema import freeze_mapping


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConversationTurn:
    """One user or assistant utterance in the current conversation."""

    turn_id: str
    role: str  # user | assistant | system
    text: str
    timestamp: str
    request_id: str | None = None
    response_id: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        object.__setattr__(self, "role", str(self.role))
        object.__setattr__(self, "text", str(self.text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "response_id": self.response_id,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def make(
        *,
        role: str,
        text: str,
        request_id: str | None = None,
        response_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ConversationTurn:
        return ConversationTurn(
            turn_id=f"turn_{uuid4().hex[:12]}",
            role=role,
            text=text,
            timestamp=_now(),
            request_id=request_id,
            response_id=response_id,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class OpenQuestion:
    """Clarification / review still waiting on Owner."""

    question_id: str
    text: str
    kind: str  # clarification | review | other
    request_id: str | None = None
    created_at: str = ""
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if not self.created_at:
            object.__setattr__(self, "created_at", _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "kind": self.kind,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ActiveWorkspaceContext:
    """
    Active workspace slice for Memory · Router · Planner (later).

    Filled by Workspace Engine in the next milestone; introduced now as contract.
    """

    workspace_id: str
    current_goal: str = ""
    active_tasks: tuple[str, ...] = ()
    current_plan: str | None = None
    current_provider: str | None = None
    preferred_model: str | None = None
    open_questions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.active_tasks, list):
            object.__setattr__(self, "active_tasks", tuple(self.active_tasks))
        if isinstance(self.open_questions, list):
            object.__setattr__(self, "open_questions", tuple(self.open_questions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "current_goal": self.current_goal,
            "active_tasks": list(self.active_tasks),
            "current_plan": self.current_plan,
            "current_provider": self.current_provider,
            "preferred_model": self.preferred_model,
            "open_questions": list(self.open_questions),
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def empty(workspace_id: str) -> ActiveWorkspaceContext:
        return ActiveWorkspaceContext(workspace_id=workspace_id)


@dataclass(frozen=True)
class ConversationMemorySnapshot:
    """Read model for ContextBuilder / Router (later wiring)."""

    session_id: str
    workspace_id: str
    turns: tuple[ConversationTurn, ...]
    open_questions: tuple[OpenQuestion, ...]
    active_workspace: ActiveWorkspaceContext
    waiting_owner: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "turns": [t.to_dict() for t in self.turns],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "active_workspace": self.active_workspace.to_dict(),
            "waiting_owner": self.waiting_owner,
            "turn_count": len(self.turns),
        }

    def as_context_fragment(self, *, max_turns: int = 20) -> dict[str, Any]:
        """Shape expected by ConversationContext.conversation window."""
        recent = self.turns[-max_turns:] if max_turns > 0 else self.turns
        return {
            "turns": [t.to_dict() for t in recent],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "waiting_owner": self.waiting_owner,
            "active_workspace": self.active_workspace.to_dict(),
            "provider": "conversation_memory",
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
        }
