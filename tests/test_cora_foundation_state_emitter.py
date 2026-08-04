"""TDD — StateEmitter (Decision → ConversationState · Harness).

Only Conversation Engine component allowed to emit ConversationState.
No Timeline, Snapshot mutation, UI, Persona, Avatar.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    ConversationHarness,
    DecisionEngine,
    PresentationHint,
    RequestValidator,
    StateEmitter,
    project_conversation_state,
    validate_state,
    reset_conversation_event_journal_for_tests,
)

SE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "state_emitter.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _decide(**req_overrides):
    raw = {
        "request_id": "req-se-1",
        "session_id": "sess-se",
        "workspace_id": "ws-nymods",
        "input": "salut",
        "barge_in": False,
        "metadata": {},
    }
    raw.update(req_overrides)
    req = RequestValidator().validate(raw)
    ctx = ContextBuilder().build(req)
    decision = DecisionEngine().decide(req, ctx)
    return req, decision


def test_respond_thinking_then_completed():
    req, decision = _decide(input="status pe NyMods")
    assert decision.tool_intent["label"] == "Respond"
    trail = StateEmitter().emit_trail(decision, req)
    assert [s.presentation for s in trail] == [
        PresentationHint.THINKING,
        PresentationHint.COMPLETED,
    ]
    final = StateEmitter().emit(decision, req)
    assert final.presentation == PresentationHint.COMPLETED


def test_ask_clarification_waiting_owner():
    req, decision = _decide(input="  ")
    assert decision.tool_intent["label"] == "AskClarification"
    state = StateEmitter().emit(decision, req)
    assert state.presentation == PresentationHint.WAITING_OWNER


def test_needs_review_waiting_owner():
    req, decision = _decide(input="", metadata={"attachments": ["a.png"]})
    assert decision.tool_intent["label"] == "NeedsReview"
    state = StateEmitter().emit(decision, req)
    assert state.presentation == PresentationHint.WAITING_OWNER


def test_refuse_completed():
    req, decision = _decide(input="x", metadata={"content_kind": "binary_blob"})
    assert decision.tool_intent["label"] == "Refuse"
    state = StateEmitter().emit(decision, req)
    assert state.presentation == PresentationHint.COMPLETED


def test_state_immutable_and_json():
    req, decision = _decide()
    state = StateEmitter().emit(decision, req)
    raw = state.to_canonical_dict()
    assert raw["schema_family"] == "cora.conversation.contracts"
    assert raw["kind"] == "ConversationState"
    again = validate_state(raw)
    assert again.presentation == state.presentation
    with pytest.raises(Exception):
        state.presentation = PresentationHint.IDLE  # type: ignore[misc]


def test_snapshot_projection_compatible():
    req, decision = _decide(input="  ")
    state = StateEmitter().emit(decision, req)
    section = project_conversation_state(state)
    assert section["source"] == "live"
    assert section["presentation"] == "WaitingOwner"
    assert section["status"] == "WaitingOwner"


def test_emit_transition():
    req, _ = _decide()
    emitter = StateEmitter()
    a = emitter.emit_transition(req, previous=None, current="Idle")
    b = emitter.emit_transition(req, previous="Idle", current="Listening")
    assert a.presentation == PresentationHint.IDLE
    assert b.presentation == PresentationHint.LISTENING


def test_harness_pass():
    h = ConversationHarness()
    assert isinstance(h.engine.state_emitter, StateEmitter)
    result = h.run_turn(
        {
            "request_id": "req-h-se",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "hello",
        }
    )
    assert result.ok is True


def test_no_ui_persona_snapshot_imports():
    forbidden = {
        "electron",
        "react",
        "persona",
        "avatar",
        "camera",
        "snapshot",
        "events",
        "gateway",
        "planner",
    }
    tree = ast.parse(SE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            if mod.startswith("..contracts") or mod == "typing" or mod.startswith("collections"):
                continue
            if mod.startswith("."):
                assert "contracts" in mod or mod in {".",}, mod
                continue
            for bad in forbidden:
                assert bad not in mod.split("."), mod
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name.lower().split(".")
