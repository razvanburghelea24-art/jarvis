"""Workspace providers — injectable storage behind WorkspaceEngine."""

from __future__ import annotations

import threading
from typing import Protocol

from .context import ActiveWorkspaceContext


class WorkspaceStore(Protocol):
    def get(self, workspace_id: str) -> ActiveWorkspaceContext | None: ...
    def put(self, ctx: ActiveWorkspaceContext) -> None: ...
    def list_ids(self) -> list[str]: ...
    def get_active(self, session_id: str) -> str | None: ...
    def set_active(self, session_id: str, workspace_id: str) -> None: ...


class InMemoryWorkspaceStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, ActiveWorkspaceContext] = {}
        self._active: dict[str, str] = {}

    def get(self, workspace_id: str) -> ActiveWorkspaceContext | None:
        with self._lock:
            return self._by_id.get(workspace_id)

    def put(self, ctx: ActiveWorkspaceContext) -> None:
        with self._lock:
            self._by_id[ctx.workspace_id] = ctx

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._by_id)

    def get_active(self, session_id: str) -> str | None:
        with self._lock:
            return self._active.get(session_id)

    def set_active(self, session_id: str, workspace_id: str) -> None:
        with self._lock:
            self._active[session_id] = workspace_id

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()
            self._active.clear()


class StubWorkspaceStore(InMemoryWorkspaceStore):
    """Injectable stub alias for tests / Harness."""
