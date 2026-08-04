"""StateEmitter — extension point (skeleton).

Will emit ConversationState for Snapshot projection. No Desktop/IPC.
"""

from __future__ import annotations

from typing import Any

from ..contracts import ConversationRequest, ConversationState
from ._skeleton import SkeletonNotImplemented


class StateEmitter:
    """Emit ConversationState (presentation/lifecycle) for Snapshot consumers."""

    def emit(
        self,
        request: ConversationRequest,
        *,
        presentation: str,
        lifecycle: str | None = None,
    ) -> ConversationState:
        # TODO: build ConversationState + SnapshotService.set_conversation_state
        raise SkeletonNotImplemented("TODO: StateEmitter.emit")

    def emit_events_hook(self, *_args: Any, **_kwargs: Any) -> None:
        """Reserved: ConversationEvents / ConversationStateChanged journal."""
        raise SkeletonNotImplemented("TODO: StateEmitter.emit_events_hook")
