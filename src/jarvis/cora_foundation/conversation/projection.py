"""Project ConversationState → Unified Snapshot conversation section.

No Engine, Planner, Gateway, LLM, or streaming — projection only.
Desktop / Persona / Avatar Director consume Snapshot, never this module directly.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import ConversationState, PresentationHint, validate_state
from .contracts.schema import SCHEMA_FAMILY, SCHEMA_VERSION


# Presentation → status string mirrored for older runtime.status consumers.
PRESENTATION_TO_STATUS: dict[str, str] = {
    PresentationHint.IDLE.value: "Idle",
    PresentationHint.LISTENING.value: "Listening",
    PresentationHint.THINKING.value: "Thinking",
    PresentationHint.PLANNING.value: "Planning",
    PresentationHint.SPEAKING.value: "Speaking",
    PresentationHint.SUCCESS.value: "Success",
    PresentationHint.WAITING.value: "Waiting",
    PresentationHint.WAITING_OWNER.value: "WaitingOwner",
    PresentationHint.COMPLETED.value: "Completed",
}


def empty_conversation_section() -> dict[str, Any]:
    return {
        "source": "off",
        "health": "off",
        "health_pct": 0.0,
        "detail": "conversation state not projected",
        "status": "Idle",
        "schema_family": SCHEMA_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "kind": "ConversationState",
        "presentation": PresentationHint.IDLE.value,
        "lifecycle": "Idle",
        "session_id": None,
        "request_id": None,
        "workspace_id": None,
        "error_class": None,
    }


def project_conversation_state(
    state: ConversationState | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Build the Snapshot `conversation` section from a validated ConversationState.

    Operator OBSERVE is never modified here.
    """
    if state is None:
        return empty_conversation_section()

    validated = state if isinstance(state, ConversationState) else validate_state(state)
    canonical = validated.to_canonical_dict()
    presentation = validated.presentation.value
    status = PRESENTATION_TO_STATUS.get(presentation, presentation)

    return {
        "source": "live",
        "health": "on",
        "health_pct": 100.0,
        "detail": f"conversation · {presentation}",
        "status": status,
        "schema_family": canonical["schema_family"],
        "schema_version": canonical["schema_version"],
        "kind": canonical["kind"],
        "session_id": validated.session_id,
        "request_id": validated.request_id,
        "workspace_id": validated.workspace_id,
        "lifecycle": validated.lifecycle.value,
        "presentation": presentation,
        "error_class": validated.error_class.value if validated.error_class else None,
    }
