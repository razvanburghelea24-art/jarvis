"""TDD — Conversation Memory (current session · not Workspace · not Core)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.conversation import (
    ActiveWorkspaceContext,
    ContextBuilder,
    ConversationMemory,
    ConversationMemoryProvider,
    RequestValidator,
    get_conversation_memory,
    reset_conversation_memory_for_tests,
)


def setup_function():
    reset_conversation_memory_for_tests()


def test_append_turns_ordered():
    mem = ConversationMemory()
    mem.bind_workspace("sess-1", "ws-nymods")
    mem.append_user("sess-1", "salut", request_id="r1")
    mem.append_assistant("sess-1", "buna", request_id="r1", response_id="resp1")
    mem.append_user("sess-1", "continuă", request_id="r2")
    snap = mem.snapshot("sess-1")
    assert len(snap.turns) == 3
    assert [t.role for t in snap.turns] == ["user", "assistant", "user"]
    assert snap.turns[0].text == "salut"
    assert snap.workspace_id == "ws-nymods"
    assert snap.waiting_owner is False


def test_open_question_waiting_owner():
    mem = get_conversation_memory()
    mem.bind_workspace("s", "ws")
    mem.add_open_question("s", "Ce vrei să fac cu atașamentul?", kind="review", request_id="r")
    snap = mem.snapshot("s")
    assert snap.waiting_owner is True
    assert len(snap.open_questions) == 1
    mem.resolve_open_questions("s")
    assert mem.snapshot("s").waiting_owner is False


def test_active_workspace_context_contract():
    ctx = ActiveWorkspaceContext(
        workspace_id="ws-nymods",
        current_goal="ship overlay",
        active_tasks=("fix-a", "fix-b"),
        current_plan=None,
        current_provider="ollama",
        preferred_model="llama3.2",
        open_questions=("clarify path?",),
    )
    raw = ctx.to_dict()
    assert raw["workspace_id"] == "ws-nymods"
    assert raw["current_provider"] == "ollama"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        ctx.workspace_id = "x"  # type: ignore[misc]


def test_memory_provider_feeds_context_builder():
    mem = get_conversation_memory()
    mem.append_user("sess-ctx", "hello", request_id="req-1", workspace_id="ws-nymods")
    mem.append_assistant("sess-ctx", "hi there", request_id="req-1", response_id="resp-1")
    builder = ContextBuilder(conversation_memory=ConversationMemoryProvider(mem))
    req = RequestValidator().validate(
        {
            "request_id": "req-2",
            "session_id": "sess-ctx",
            "workspace_id": "ws-nymods",
            "input": "next",
        }
    )
    ctx = builder.build(req)
    turns = ctx.conversation.get("turns") or []
    assert len(turns) >= 2
    assert turns[0]["text"] == "hello"
    assert ctx.conversation.get("provider") == "conversation_memory"
    assert ctx.conversation.get("active_workspace", {}).get("workspace_id") == "ws-nymods"


def test_sessions_are_isolated():
    mem = ConversationMemory()
    mem.append_user("a", "only-a", workspace_id="ws-a")
    mem.append_user("b", "only-b", workspace_id="ws-b")
    assert mem.snapshot("a").turns[0].text == "only-a"
    assert mem.snapshot("b").turns[0].text == "only-b"


def test_snapshot_json_serializable():
    mem = ConversationMemory()
    mem.append_user("s", "x", workspace_id="w")
    raw = mem.snapshot("s").to_dict()
    assert json.loads(json.dumps(raw))["turn_count"] == 1
