"""ConversationState → Snapshot projection (no Engine)."""

from __future__ import annotations

from src.jarvis.cora_foundation.conversation import (
    ConversationState,
    LifecyclePhase,
    PresentationHint,
    project_conversation_state,
    reset_conversation_event_journal_for_tests,
)
from src.jarvis.cora_foundation.snapshot import SnapshotService, reset_snapshot_service_for_tests


def setup_function():
    reset_snapshot_service_for_tests()
    reset_conversation_event_journal_for_tests()


def _state(presentation: str, *, lifecycle: str | None = None) -> ConversationState:
    return ConversationState(
        session_id="sess-proj",
        request_id="req-proj",
        workspace_id="ws-nymods",
        lifecycle=LifecyclePhase(lifecycle or "Thinking"),
        presentation=PresentationHint(presentation),
    )


def test_project_conversation_state_shape():
    section = project_conversation_state(_state("Planning", lifecycle="Thinking"))
    assert section["source"] == "live"
    assert section["kind"] == "ConversationState"
    assert section["schema_family"] == "cora.conversation.contracts"
    assert section["schema_version"] == 1
    assert section["presentation"] == "Planning"
    assert section["status"] == "Planning"
    assert section["workspace_id"] == "ws-nymods"


def test_snapshot_service_projects_conversation_sequence():
    svc = SnapshotService(enabled=True)
    trail = []
    for presentation in (
        "Idle",
        "Listening",
        "Thinking",
        "Planning",
        "WaitingOwner",
        "Completed",
    ):
        lifecycle = {
            "Idle": "Idle",
            "Listening": "Listening",
            "Thinking": "Thinking",
            "Planning": "Thinking",
            "WaitingOwner": "Streaming",
            "Completed": "Completed",
        }[presentation]
        svc.set_conversation_state(_state(presentation, lifecycle=lifecycle))
        snap = svc.build()
        assert snap.conversation["source"] == "live"
        assert snap.conversation["presentation"] == presentation
        assert snap.runtime["status"] == presentation
        assert snap.operator["indicator"] == "OBSERVE"
        assert snap.operator["controls"] is False
        trail.append(snap.conversation["presentation"])
        exported = snap.to_dict()
        assert "conversation" in exported
        assert exported["conversation"]["presentation"] == presentation

    assert trail == [
        "Idle",
        "Listening",
        "Thinking",
        "Planning",
        "WaitingOwner",
        "Completed",
    ]


def test_clear_conversation_state():
    svc = SnapshotService(enabled=True)
    svc.set_conversation_state(_state("Listening", lifecycle="Listening"))
    assert svc.build().conversation["source"] == "live"
    svc.clear_conversation_state()
    snap = svc.build()
    assert snap.conversation["source"] == "off"
    assert snap.conversation["presentation"] == "Idle"
