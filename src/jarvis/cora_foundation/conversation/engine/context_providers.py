"""ContextProvider stubs — injectable data sources for ContextBuilder.

ContextBuilder never talks to GitHub/Discord/Electron/Planner.
Replace Stub* later with Local/Redis/SQL/Cloud providers without changing the builder.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..contracts import ConversationRequest

DEFAULT_LIMITS: dict[str, Any] = {
    "max_turns": 20,
    "max_tokens_estimate": 4096,
    "provider": "stub",
}


class ContextProvider(Protocol):
    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        """Return a dict fragment for one context window."""


class StubConversationMemoryProvider:
    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        return {
            "turns": [],
            "open_questions": [],
            "provider": "stub",
            "workspace_id": request.workspace_id,
            "session_id": request.session_id,
        }


class StubWorkspaceProvider:
    """Provides active_workspace + workspace_memory stubs."""

    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        return {
            "active": {
                "workspace_id": request.workspace_id,
                "name": request.workspace_id,
                "provider": "stub",
            },
            "memory": {
                "facts": [],
                "open_tasks": [],
                "provider": "stub",
            },
        }


class StubCoreMemoryProvider:
    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        return {
            "entries": [],
            "identity": {},
            "policies": {},
            "provider": "stub",
        }


class StubRuntimeSnapshotProvider:
    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        return {
            "status": "Idle",
            "e_stop": False,
            "operator": "OBSERVE",
            "provider": "stub",
            "request_id": request.request_id,
        }
