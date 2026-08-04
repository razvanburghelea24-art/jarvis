"""WorkspaceEngine — sole producer of ActiveWorkspaceContext.

No LLM · Electron · Conversation Memory · Planner · Tools · Router.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..conversation.contracts import ConversationRequest
from .context import ActiveWorkspaceContext
from .providers import InMemoryWorkspaceStore, WorkspaceStore


class WorkspaceEngine:
    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self.store = store or InMemoryWorkspaceStore()

    def create(
        self,
        workspace_id: str,
        *,
        workspace_name: str = "",
        workspace_type: str = "general",
        metadata: Mapping[str, Any] | None = None,
    ) -> ActiveWorkspaceContext:
        existing = self.store.get(workspace_id)
        if existing is not None:
            return existing
        ctx = ActiveWorkspaceContext(
            workspace_id=workspace_id,
            workspace_name=workspace_name or workspace_id,
            workspace_type=workspace_type,
            metadata=dict(metadata or {}),
        )
        self.store.put(ctx)
        return ctx

    def switch(self, session_id: str, workspace_id: str) -> ActiveWorkspaceContext:
        ctx = self.store.get(workspace_id) or self.create(workspace_id)
        self.store.set_active(session_id, workspace_id)
        return ctx

    def ensure_active(self, session_id: str, workspace_id: str) -> ActiveWorkspaceContext:
        active = self.store.get_active(session_id)
        if active != workspace_id:
            return self.switch(session_id, workspace_id)
        ctx = self.store.get(active) if active else None
        return ctx if ctx is not None else self.switch(session_id, workspace_id)

    def get_context(self, session_id: str) -> ActiveWorkspaceContext | None:
        wid = self.store.get_active(session_id)
        return self.store.get(wid) if wid else None

    def require_context(self, session_id: str) -> ActiveWorkspaceContext:
        ctx = self.get_context(session_id)
        if ctx is None:
            raise LookupError(f"no active workspace for session {session_id!r}")
        return ctx

    def update_goal(self, session_id: str, goal: str) -> ActiveWorkspaceContext:
        return self._mutate(session_id, current_goal=str(goal))

    def set_plan(self, session_id: str, plan: str | None) -> ActiveWorkspaceContext:
        return self._mutate(session_id, active_plan=plan)

    def add_task(self, session_id: str, task: str) -> ActiveWorkspaceContext:
        ctx = self.require_context(session_id)
        tasks = list(ctx.active_tasks)
        if task not in tasks:
            tasks.append(task)
        return self._mutate(session_id, active_tasks=tuple(tasks))

    def close_task(self, session_id: str, task: str) -> ActiveWorkspaceContext:
        ctx = self.require_context(session_id)
        return self._mutate(
            session_id,
            active_tasks=tuple(t for t in ctx.active_tasks if t != task),
        )

    def add_open_question(self, session_id: str, question: str) -> ActiveWorkspaceContext:
        ctx = self.require_context(session_id)
        qs = list(ctx.open_questions)
        if question not in qs:
            qs.append(question)
        return self._mutate(session_id, open_questions=tuple(qs))

    def clear_open_questions(self, session_id: str) -> ActiveWorkspaceContext:
        return self._mutate(session_id, open_questions=())

    def set_preferences(
        self,
        session_id: str,
        *,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
    ) -> ActiveWorkspaceContext:
        changes: dict[str, Any] = {}
        if preferred_provider is not None:
            changes["preferred_provider"] = preferred_provider
        if preferred_model is not None:
            changes["preferred_model"] = preferred_model
        return self._mutate(session_id, **changes)

    def _mutate(self, session_id: str, **changes: Any) -> ActiveWorkspaceContext:
        nxt = self.require_context(session_id).evolve(**changes)
        self.store.put(nxt)
        return nxt


class WorkspaceEngineProvider:
    """ContextBuilder workspace window from WorkspaceEngine."""

    def __init__(self, engine: WorkspaceEngine | None = None) -> None:
        self.engine = engine or WorkspaceEngine()

    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        ctx = self.engine.ensure_active(request.session_id, request.workspace_id)
        return {
            "active": ctx.to_dict(),
            "memory": {
                "facts": [],
                "open_tasks": list(ctx.active_tasks),
                "provider": "workspace_engine",
            },
            "provider": "workspace_engine",
        }
