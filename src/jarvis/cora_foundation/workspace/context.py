"""ActiveWorkspaceContext — frozen contract for Memory · Router · Planner · Tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ..conversation.contracts.schema import freeze_mapping


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ActiveWorkspaceContext:
    """Answers: In what project context is Cora working now?"""

    workspace_id: str
    workspace_name: str = ""
    workspace_type: str = "general"
    current_goal: str = ""
    active_plan: str | None = None
    active_tasks: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    preferred_provider: str | None = None
    preferred_model: str | None = None
    capabilities: tuple[str, ...] = ()
    conversation_scope: str = "session"
    created_at: str = ""
    updated_at: str = ""
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        for name in ("active_tasks", "open_questions", "capabilities"):
            val = getattr(self, name)
            if isinstance(val, list):
                object.__setattr__(self, name, tuple(val))
        if not self.workspace_name:
            object.__setattr__(self, "workspace_name", self.workspace_id)
        ts = _now()
        if not self.created_at:
            object.__setattr__(self, "created_at", ts)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", self.created_at or ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "workspace_type": self.workspace_type,
            "current_goal": self.current_goal,
            "active_plan": self.active_plan,
            "active_tasks": list(self.active_tasks),
            "open_questions": list(self.open_questions),
            "preferred_provider": self.preferred_provider,
            "preferred_model": self.preferred_model,
            "capabilities": list(self.capabilities),
            "conversation_scope": self.conversation_scope,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    def evolve(self, **changes: Any) -> ActiveWorkspaceContext:
        data = self.to_dict()
        data.update(changes)
        data["updated_at"] = _now()
        data["created_at"] = self.created_at
        return ActiveWorkspaceContext(**data)

    @staticmethod
    def empty(
        workspace_id: str,
        *,
        workspace_name: str = "",
        workspace_type: str = "general",
    ) -> ActiveWorkspaceContext:
        return ActiveWorkspaceContext(
            workspace_id=workspace_id,
            workspace_name=workspace_name or workspace_id,
            workspace_type=workspace_type,
        )
