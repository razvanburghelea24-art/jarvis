"""In-process Conversation Memory store — session-scoped turns.

Does not write Core Memory · Workspace Memory · Audit · Snapshot.
"""

from __future__ import annotations

import threading
from uuid import uuid4

from .types import (
    ActiveWorkspaceContext,
    ConversationMemorySnapshot,
    ConversationTurn,
    OpenQuestion,
)


class ConversationMemory:
    """Current-conversation journal for one process (tests / Harness / local Core)."""

    def __init__(self, *, max_turns: int = 100) -> None:
        self._max_turns = max(1, int(max_turns))
        self._lock = threading.RLock()
        # session_id → state
        self._turns: dict[str, list[ConversationTurn]] = {}
        self._open: dict[str, list[OpenQuestion]] = {}
        self._workspace: dict[str, str] = {}
        self._active: dict[str, ActiveWorkspaceContext] = {}

    def clear(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._turns.clear()
                self._open.clear()
                self._workspace.clear()
                self._active.clear()
                return
            self._turns.pop(session_id, None)
            self._open.pop(session_id, None)
            self._workspace.pop(session_id, None)
            self._active.pop(session_id, None)

    def bind_workspace(self, session_id: str, workspace_id: str) -> None:
        with self._lock:
            self._workspace[session_id] = workspace_id
            if session_id not in self._active:
                self._active[session_id] = ActiveWorkspaceContext.empty(workspace_id)
            elif self._active[session_id].workspace_id != workspace_id:
                prev = self._active[session_id]
                self._active[session_id] = ActiveWorkspaceContext(
                    workspace_id=workspace_id,
                    current_goal=prev.current_goal,
                    active_tasks=prev.active_tasks,
                    current_plan=prev.current_plan,
                    current_provider=prev.current_provider,
                    preferred_model=prev.preferred_model,
                    open_questions=prev.open_questions,
                    metadata=dict(prev.metadata),
                )

    def set_active_workspace(self, session_id: str, ctx: ActiveWorkspaceContext) -> None:
        with self._lock:
            self._active[session_id] = ctx
            self._workspace[session_id] = ctx.workspace_id

    def append_user(
        self,
        session_id: str,
        text: str,
        *,
        request_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ConversationTurn:
        if workspace_id:
            self.bind_workspace(session_id, workspace_id)
        turn = ConversationTurn.make(role="user", text=text, request_id=request_id)
        self._append(session_id, turn)
        return turn

    def append_assistant(
        self,
        session_id: str,
        text: str,
        *,
        request_id: str | None = None,
        response_id: str | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn.make(
            role="assistant",
            text=text,
            request_id=request_id,
            response_id=response_id,
        )
        self._append(session_id, turn)
        return turn

    def add_open_question(
        self,
        session_id: str,
        text: str,
        *,
        kind: str = "clarification",
        request_id: str | None = None,
    ) -> OpenQuestion:
        q = OpenQuestion(
            question_id=f"oq_{uuid4().hex[:12]}",
            text=text,
            kind=kind,
            request_id=request_id,
        )
        with self._lock:
            self._open.setdefault(session_id, []).append(q)
        return q

    def resolve_open_questions(self, session_id: str) -> None:
        with self._lock:
            self._open[session_id] = []

    def snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        with self._lock:
            turns = tuple(self._turns.get(session_id, []))
            open_q = tuple(self._open.get(session_id, []))
            ws = self._workspace.get(session_id, "")
            active = self._active.get(session_id) or ActiveWorkspaceContext.empty(ws or "unknown")
            return ConversationMemorySnapshot(
                session_id=session_id,
                workspace_id=active.workspace_id or ws,
                turns=turns,
                open_questions=open_q,
                active_workspace=active,
                waiting_owner=bool(open_q),
            )

    def _append(self, session_id: str, turn: ConversationTurn) -> None:
        with self._lock:
            bucket = self._turns.setdefault(session_id, [])
            bucket.append(turn)
            if len(bucket) > self._max_turns:
                self._turns[session_id] = bucket[-self._max_turns :]


_STORE: ConversationMemory | None = None
_LOCK = threading.Lock()


def get_conversation_memory() -> ConversationMemory:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = ConversationMemory()
        return _STORE


def reset_conversation_memory_for_tests() -> None:
    global _STORE
    with _LOCK:
        if _STORE is not None:
            _STORE.clear()
        _STORE = None
