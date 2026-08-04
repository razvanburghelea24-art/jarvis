"""Conversation Memory types — current session turns only.

ActiveWorkspaceContext SSOT lives in cora_foundation.workspace.context
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from ..contracts.schema import freeze_mapping
from ...workspace.context import ActiveWorkspaceContext

__all__ = [
    "ActiveWorkspaceContext",
    "ConversationMemorySnapshot",
    "ConversationTurn",
    "OpenQuestion",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    role: str
    text: str
    timestamp: str
    request_id: str | None = None
    response_id: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

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
    question_id: str
    text: str
    kind: str
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
class ConversationMemorySnapshot:
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
