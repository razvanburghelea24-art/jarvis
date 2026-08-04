"""Beta 1A — Conversation Engine Test Harness DoD."""

from __future__ import annotations

from src.jarvis.cora_foundation.conversation import (
    ConversationHarness,
    reset_conversation_event_journal_for_tests,
)
from src.jarvis.cora_foundation.conversation.events import EVENT_CONVERSATION_STATE_CHANGED
from src.jarvis.cora_foundation.gateway import reset_command_gateway_for_tests


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_command_gateway_for_tests()


def _valid_payload(**overrides):
    base = {
        "request_id": "req-harness-1",
        "session_id": "sess-harness",
        "workspace_id": "ws-nymods",
        "input": "hello harness",
        "barge_in": False,
    }
    base.update(overrides)
    return base


def test_1_valid_request_pass():
    h = ConversationHarness()
    result = h.accept(_valid_payload())
    assert result.ok is True
    assert result.status_code == 200
    assert result.code == "OK"
    assert result.request is not None


def test_2_invalid_request_fail():
    h = ConversationHarness()
    result = h.accept(_valid_payload(workspace_id=""))
    assert result.ok is False
    assert result.status_code == 400
    assert result.code == "INVALID_REQUEST"


def test_3_state_idle_to_listening():
    h = ConversationHarness()
    accepted = h.accept(_valid_payload())
    assert accepted.request is not None
    states = h.emit_state_sequence(accepted.request, ["Idle", "Listening"])
    assert [s.presentation.value for s in states] == ["Idle", "Listening"]


def test_4_placeholder_conversation_response():
    h = ConversationHarness()
    result = h.run_turn(_valid_payload(request_id="req-placeholder-resp"))
    assert result.ok is True
    assert result.response is not None
    assert result.response.text.strip() != ""
    assert result.response.metadata.get("response_mode") == "placeholder"
    assert result.response.to_canonical_dict()["kind"] == "ConversationResponse"
    assert result.response.to_canonical_dict()["schema_family"] == "cora.conversation.contracts"


def test_5_timeline_receives_conversation_state_changed():
    h = ConversationHarness()
    result = h.run_turn(_valid_payload(request_id="req-timeline"))
    assert result.ok is True
    assert h.timeline_has_state_changed(current_state="Listening")
    events = result.to_dict()["events"]
    assert any(e["event_type"] == EVENT_CONVERSATION_STATE_CHANGED for e in events)
    assert any(e["current_state"] == "Listening" for e in events)
    assert any(e.get("previous_state") == "Idle" for e in events)
