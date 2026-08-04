"""TDD — ConversationEvents (conversation journal · not Audit · not StateEmitter).

Engine emits only. EventJournal observes via on_event. No Snapshot / Persona / IPC.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ConversationEngine,
    ConversationEvent,
    ConversationEvents,
    ConversationHarness,
    EventJournal,
    CONTEXT_BUILT,
    CONVERSATION_COMPLETED,
    DECISION_MADE,
    PIPELINE_ORDER,
    REQUEST_ACCEPTED,
    REQUEST_VALIDATED,
    RESPONSE_BUILT,
    STATE_EMITTED,
    reset_conversation_event_journal_for_tests,
)

CE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "conversation_events.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def test_pipeline_events_in_order_via_harness():
    h = ConversationHarness()
    result = h.run_turn(
        {
            "request_id": "req-ce-1",
            "session_id": "sess-ce",
            "workspace_id": "ws-nymods",
            "input": "hello events",
        }
    )
    assert result.ok is True
    types = h.event_journal.types(request_id="req-ce-1")
    assert types == list(PIPELINE_ORDER)
    assert types[0] == REQUEST_ACCEPTED
    assert REQUEST_VALIDATED in types
    assert CONTEXT_BUILT in types
    assert DECISION_MADE in types
    assert STATE_EMITTED in types
    assert RESPONSE_BUILT in types
    assert types[-1] == CONVERSATION_COMPLETED


def test_each_event_type_payload():
    journal = EventJournal()
    events = ConversationEvents(on_event=journal.record)
    engine = ConversationEngine(conversation_events=events)
    req = {
        "request_id": "req-ce-2",
        "session_id": "s",
        "workspace_id": "w",
        "input": "status",
    }
    # Engine spine does not emit REQUEST_ACCEPTED (Gateway/Harness)
    events.request_accepted(engine.validate(req))
    engine.submit(req)
    by_type = {e.type: e for e in journal.events() if e.request_id == "req-ce-2"}
    types = [e.type for e in journal.events() if e.request_id == "req-ce-2"]
    assert REQUEST_ACCEPTED in types
    assert REQUEST_VALIDATED in types
    assert by_type[DECISION_MADE].payload.get("label") == "Respond"
    assert by_type[STATE_EMITTED].payload.get("presentation")
    assert by_type[RESPONSE_BUILT].payload.get("response_id")
    assert by_type[CONVERSATION_COMPLETED].payload.get("response_id")


def test_event_immutable_and_json():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    engine = ConversationEngine(conversation_events=bus)
    req = engine.validate(
        {
            "request_id": "req-ce-json",
            "session_id": "s",
            "workspace_id": "w",
            "input": "x",
        }
    )
    ev = bus.request_validated(req)
    assert isinstance(ev, ConversationEvent)
    raw = ev.to_dict()
    assert set(raw) >= {
        "event_id",
        "request_id",
        "workspace_id",
        "session_id",
        "timestamp",
        "type",
        "payload",
        "metadata",
    }
    assert json.dumps(raw)
    again = json.loads(json.dumps(raw))
    assert again["type"] == REQUEST_VALIDATED
    with pytest.raises(Exception):
        ev.type = "MUTATED"  # type: ignore[misc]


def test_chronological_order():
    h = ConversationHarness()
    h.run_turn(
        {
            "request_id": "req-ce-ord",
            "session_id": "s",
            "workspace_id": "w",
            "input": "ord",
        }
    )
    events = [e for e in h.event_journal.events() if e.request_id == "req-ce-ord"]
    stamps = [e.timestamp for e in events]
    assert stamps == sorted(stamps)
    assert [e.type for e in events] == list(PIPELINE_ORDER)


def test_does_not_write_audit_or_timeline_modules():
    forbidden = {
        "audit_hooks",
        "persona",
        "electron",
        "react",
        "avatar",
        "snapshot",
        "projection",
        "gateway",
        "openai",
        "httpx",
    }
    tree = ast.parse(CE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            if mod.startswith(".") or "contracts" in mod:
                continue
            for bad in forbidden:
                assert bad not in mod.split("."), mod
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name.lower().split(".")


def test_observer_pattern_engine_does_not_own_listeners():
    seen: list[str] = []
    bus = ConversationEvents(on_event=lambda e: seen.append(e.type))
    engine = ConversationEngine(conversation_events=bus)
    engine.submit(
        {
            "request_id": "req-ce-obs",
            "session_id": "s",
            "workspace_id": "w",
            "input": "hi",
        }
    )
    assert REQUEST_VALIDATED in seen
    assert CONVERSATION_COMPLETED in seen
    assert REQUEST_ACCEPTED not in seen  # Gateway/Harness only


def test_harness_pass_exposes_journal():
    h = ConversationHarness()
    result = h.run_turn(
        {
            "request_id": "req-ce-h",
            "session_id": "s",
            "workspace_id": "w",
            "input": "harness",
        }
    )
    assert result.ok is True
    dumped = result.to_dict()
    assert "conversation_events" in dumped
    types = [e["type"] for e in dumped["conversation_events"] if e["request_id"] == "req-ce-h"]
    assert types == list(PIPELINE_ORDER)
    assert isinstance(h.engine.conversation_events, ConversationEvents)
