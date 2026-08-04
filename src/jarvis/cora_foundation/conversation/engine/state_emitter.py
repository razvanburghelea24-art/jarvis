"""StateEmitter — Decision → ConversationState (only Engine component allowed).

Deterministic mapping. No Timeline, Snapshot writes, UI, Persona, Avatar, Camera.
Optional on_state sink may observe published states (wired by Harness / Snapshot later).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..contracts import (
    ConversationDecision,
    ConversationRequest,
    ConversationState,
    LifecyclePhase,
    PresentationHint,
)

# Decision label (from DecisionEngine tool_intent) → presentation trail
_LABEL_TRAIL: dict[str, tuple[str, ...]] = {
    "AskClarification": ("WaitingOwner",),
    "NeedsReview": ("WaitingOwner",),
    "Refuse": ("Completed",),
    "Respond": ("Thinking", "Completed"),
}

_PRESENTATION_LIFECYCLE: dict[str, str] = {
    "Idle": "Idle",
    "Listening": "Listening",
    "Thinking": "Thinking",
    "WaitingOwner": "Streaming",
    "Completed": "Completed",
    "Speaking": "Streaming",
    "Success": "Completed",
    "Waiting": "Streaming",
    "Planning": "Thinking",
}


class StateEmitter:
    """Publish ConversationState from decisions / explicit transitions."""

    def __init__(
        self,
        *,
        on_state: Callable[[ConversationState], None] | None = None,
    ) -> None:
        self._on_state = on_state

    def emit(self, decision: ConversationDecision, request: ConversationRequest) -> ConversationState:
        """Emit final ConversationState for a decision (last step of trail)."""
        trail = self.emit_trail(decision, request)
        return trail[-1]

    def emit_trail(
        self,
        decision: ConversationDecision,
        request: ConversationRequest,
    ) -> list[ConversationState]:
        """Full presentation trail (e.g. Respond → Thinking → Completed). No streaming."""
        label = str(decision.tool_intent.get("label") or decision.tool_intent.get("decision") or "")
        presentations = _LABEL_TRAIL.get(label)
        if not presentations:
            # Fallback from kind
            if decision.kind.value == "clarify":
                presentations = ("WaitingOwner",)
            elif decision.kind.value == "refuse":
                presentations = ("Completed",)
            else:
                presentations = ("Thinking", "Completed")

        out: list[ConversationState] = []
        previous: str | None = None
        for presentation in presentations:
            state = self.emit_transition(
                request,
                previous=previous,
                current=presentation,
            )
            out.append(state)
            previous = presentation
        return out

    def emit_transition(
        self,
        request: ConversationRequest,
        *,
        previous: str | None,
        current: str,
        lifecycle: str | None = None,
    ) -> ConversationState:
        """Publish one ConversationState transition (history-friendly)."""
        life = lifecycle or _PRESENTATION_LIFECYCLE.get(current, "Thinking")
        state = ConversationState(
            session_id=request.session_id,
            request_id=request.request_id,
            workspace_id=request.workspace_id,
            lifecycle=LifecyclePhase(life),
            presentation=PresentationHint(current),
        )
        # Observe only — never Timeline/Snapshot modules here
        if self._on_state is not None:
            self._on_state(state)
        # previous is recorded by ConversationEvents later; keep API for callers
        _ = previous
        return state
