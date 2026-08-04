"""E2E — Router Wiring (Beta Foundation official pipeline)."""

from __future__ import annotations

from src.jarvis.cora_foundation.conversation import (
    WiredConversationPipeline,
    reset_conversation_event_journal_for_tests,
    reset_conversation_memory_for_tests,
)
from src.jarvis.cora_foundation.llm import ModelRouter, RouteNeeds, routing_test_registry
from src.jarvis.cora_foundation.workspace import StubWorkspaceStore, WorkspaceEngine


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _pipeline(**kwargs) -> WiredConversationPipeline:
    ws = kwargs.pop("workspace", None) or WorkspaceEngine(StubWorkspaceStore())
    router = kwargs.pop("router", None) or ModelRouter(routing_test_registry())
    return WiredConversationPipeline(workspace=ws, router=router, **kwargs)


def test_e2e_simple_prompt_mock_path():
    p = _pipeline()
    # force general → any available; use offline for deterministic ollama in test registry
    result = p.run(
        {
            "request_id": "req-e2e-1",
            "session_id": "sess-e2e",
            "workspace_id": "ws-nymods",
            "input": "salut Cora",
        },
        needs_override=RouteNeeds(require_offline=True, reasoning=6),
        stream=True,
    )
    assert result.ok is True
    assert result.response is not None
    assert result.response.metadata.get("response_mode") == "llm"
    assert result.route is not None
    assert result.route.provider_id == "ollama"
    assert result.llm is not None
    assert result.stream is not None
    assert result.stream.completed is True
    assert "".join(c.text for c in result.stream.chunks) == result.response.text


def test_e2e_workspace_reaches_router_context():
    ws = WorkspaceEngine(StubWorkspaceStore())
    ws.create("ws-nymods", workspace_name="NyMods", workspace_type="coding")
    p = _pipeline(workspace=ws)
    result = p.run(
        {
            "request_id": "req-e2e-ws",
            "session_id": "sess-ws",
            "workspace_id": "ws-nymods",
            "input": "fix the overlay bug",
        },
        stream=False,
    )
    assert result.ok is True
    active = result.context.workspace["active"]
    assert active["workspace_id"] == "ws-nymods"
    assert active["workspace_type"] == "coding"
    assert active["workspace_name"] == "NyMods"
    # coding workspace → Claude via needs_from_context
    assert result.route.provider_id == "claude"


def test_e2e_offline_chooses_ollama():
    ws = WorkspaceEngine(StubWorkspaceStore())
    ws.create("ws-casual", workspace_type="casual")
    p = _pipeline(workspace=ws)
    result = p.run(
        {
            "request_id": "req-off",
            "session_id": "sess-off",
            "workspace_id": "ws-casual",
            "input": "hello",
        },
        stream=False,
    )
    assert result.ok is True
    assert result.route.provider_id == "ollama"


def test_e2e_coding_chooses_claude():
    ws = WorkspaceEngine(StubWorkspaceStore())
    ws.create("ws-code", workspace_type="coding")
    p = _pipeline(workspace=ws)
    result = p.run(
        {
            "request_id": "req-code",
            "session_id": "sess-code",
            "workspace_id": "ws-code",
            "input": "refactor this function",
        },
        stream=False,
    )
    assert result.route.provider_id == "claude"
    assert result.llm.provider == "claude"


def test_e2e_unavailable_falls_back():
    # Mock cannot stream → require_streaming yields no eligible match → router fallback
    from src.jarvis.cora_foundation.llm import CAPABILITY_MOCK, MockLLMProvider, ProviderRegistry

    reg = ProviderRegistry()
    reg.register(MockLLMProvider(), CAPABILITY_MOCK)
    p = _pipeline(router=ModelRouter(reg))
    result = p.run(
        {
            "request_id": "req-fb",
            "session_id": "sess-fb",
            "workspace_id": "ws",
            "input": "hi",
        },
        needs_override=RouteNeeds(require_streaming=True),
        stream=False,
    )
    assert result.ok is True
    assert result.route.provider_id == "mock"
    assert result.route.reason == "fallback_no_match"


def test_e2e_invalid_stops_at_validator():
    p = _pipeline()
    result = p.run(
        {
            "request_id": "req-bad",
            "session_id": "sess-bad",
            "workspace_id": "",
            "input": "x",
        }
    )
    assert result.ok is False
    assert result.response is None
    assert result.errors
