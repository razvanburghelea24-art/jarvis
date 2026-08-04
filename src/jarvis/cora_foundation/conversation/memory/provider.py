"""ContextBuilder provider backed by ConversationMemory (not Stub)."""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import ConversationRequest
from .store import ConversationMemory, get_conversation_memory


class ConversationMemoryProvider:
    """Fetches current-session conversation window for ContextBuilder."""

    def __init__(
        self,
        memory: ConversationMemory | None = None,
        *,
        max_turns: int = 20,
    ) -> None:
        self._memory = memory or get_conversation_memory()
        self._max_turns = max_turns

    def fetch(self, request: ConversationRequest) -> Mapping[str, Any]:
        self._memory.bind_workspace(request.session_id, request.workspace_id)
        snap = self._memory.snapshot(request.session_id)
        return snap.as_context_fragment(max_turns=self._max_turns)
