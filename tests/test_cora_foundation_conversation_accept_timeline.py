"""ConversationStateChanged timeline + Gateway Accept (validate-only)."""

from __future__ import annotations

from src.jarvis.cora_foundation.conversation import (
    ConversationState,
    LifecyclePhase,
    PresentationHint,
    reset_conversation_event_journal_for_tests,
)
from src.jarvis.cora_foundation.gateway import (
    CommandGateway,
    reset_command_gateway_for_tests,
)
from src.jarvis.cora_foundation.gateway.audit_hooks import AuditJournal
from src.jarvis.cora_foundation.snapshot import SnapshotService, reset_snapshot_service_for_tests


def setup_function():
    reset_snapshot_service_for_tests()
    reset_conversation_event_journal_for_tests()
    reset_command_gateway_for_tests()


def _state(presentation: str) -> ConversationState:
    life = {
        "Idle": "Idle",
        "Listening": "Listening",
        "Thinking": "Thinking",
        "Planning": "Thinking",
        "WaitingOwner": "Streaming",
        "Completed": "Completed",
    }.get(presentation, "Thinking")
    return ConversationState(
        session_id="sess-ev",
        request_id="req-ev",
        workspace_id="ws-nymods",
        lifecycle=LifecyclePhase(life),
        presentation=PresentationHint(presentation),
    )


def test_conversation_state_changed_timeline():
    svc = SnapshotService(enabled=True)
    seq = ["Idle", "Listening", "Thinking", "Planning", "WaitingOwner", "Completed"]
    for p in seq:
        svc.set_conversation_state(_state(p))
    snap = svc.build()
    events = snap.conversation["events"]
    assert len(events) >= 6
    current = [e["current_state"] for e in events[-6:]]
    assert current == seq
    for e in events[-6:]:
        assert e["event_type"] == "ConversationStateChanged"
        assert "timestamp" in e
        assert "previous_state" in e
        assert e["request_id"] == "req-ev"
        assert e["workspace_id"] == "ws-nymods"


def test_no_duplicate_event_when_same_state():
    svc = SnapshotService(enabled=True)
    svc.set_conversation_state(_state("Listening"))
    svc.set_conversation_state(_state("Listening"))
    events = svc.build().conversation["events"]
    listening = [e for e in events if e["current_state"] == "Listening"]
    assert len(listening) == 1


def test_gateway_accept_ok():
    gw = CommandGateway(enabled=True)
    result = gw.accept_conversation_request(
        {
            "request_id": "req-ok",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "salut",
            "barge_in": False,
        }
    )
    assert result.ok is True
    assert result.status_code == 200
    assert result.code == "OK"
    assert result.request is not None
    assert result.audited is True
    types = [e.event_type for e in gw.audit.events()]
    assert AuditJournal.REQUEST_RECEIVED in types
    assert AuditJournal.REQUEST_COMPLETED in types
    # Ensure accept path did not run command pipeline markers that imply tools
    payload = gw.audit.events()[-1].payload
    assert payload.get("engine_invoked") is False
    assert payload.get("planner_invoked") is False
    assert payload.get("llm_invoked") is False
    assert payload.get("tools_invoked") is False


def test_gateway_accept_invalid():
    gw = CommandGateway(enabled=True)
    result = gw.accept_conversation_request(
        {
            "request_id": "req-bad",
            "session_id": "sess-1",
            "workspace_id": "",
            "input": "x",
        }
    )
    assert result.ok is False
    assert result.status_code == 400
    assert result.code == "INVALID_REQUEST"
    types = [e.event_type for e in gw.audit.events()]
    assert AuditJournal.REQUEST_FAILED in types
