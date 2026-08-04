"""TDD — ContextBuilder (stub ContextProviders · Harness).

Single responsibility: ConversationRequest → ConversationContext.
Does not decide, respond, plan, or emit state.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    ConversationContext,
    ConversationHarness,
    ConversationRequest,
    RequestValidator,
    StubConversationMemoryProvider,
    StubCoreMemoryProvider,
    StubRuntimeSnapshotProvider,
    StubWorkspaceProvider,
    validate_context,
    reset_conversation_event_journal_for_tests,
)

CB_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _request(**overrides) -> ConversationRequest:
    raw = {
        "request_id": "req-ctx-1",
        "session_id": "sess-ctx",
        "workspace_id": "ws-nymods",
        "input": "ce știi despre proiect?",
        "barge_in": False,
        "metadata": {"source": "harness", "trace": "t1"},
    }
    raw.update(overrides)
    return RequestValidator().validate(raw)


def test_request_to_context():
    ctx = ContextBuilder().build(_request())
    assert isinstance(ctx, ConversationContext)
    assert ctx.request_id == "req-ctx-1"
    assert ctx.session_id == "sess-ctx"
    assert ctx.workspace_id == "ws-nymods"
    assert ctx.sealed is True


def test_default_workspace_section():
    ctx = ContextBuilder().build(_request())
    assert "active" in ctx.workspace
    assert ctx.workspace["active"]["workspace_id"] == "ws-nymods"
    assert "memory" in ctx.workspace


def test_conversation_memory_empty_stub():
    ctx = ContextBuilder().build(_request())
    assert "memory" in ctx.conversation
    assert ctx.conversation["memory"]["turns"] == []
    assert ctx.conversation["memory"]["provider"] == "stub"


def test_core_memory_empty_stub():
    ctx = ContextBuilder().build(_request())
    assert "memory" in ctx.core
    assert ctx.core["memory"]["entries"] == []
    assert ctx.core["memory"]["provider"] == "stub"


def test_runtime_snapshot_empty_stub():
    ctx = ContextBuilder().build(_request())
    assert "snapshot" in ctx.runtime
    assert ctx.runtime["snapshot"]["status"] == "Idle"
    assert ctx.runtime["snapshot"]["provider"] == "stub"


def test_metadata_copied():
    ctx = ContextBuilder().build(_request())
    assert ctx.conversation["metadata"]["source"] == "harness"
    assert ctx.conversation["metadata"]["trace"] == "t1"
    assert "request" in ctx.conversation
    assert ctx.conversation["request"]["input"] == "ce știi despre proiect?"
    assert "limits" in ctx.conversation


def test_request_remains_immutable():
    req = _request()
    before = req.to_canonical_dict()
    ContextBuilder().build(req)
    assert req.to_canonical_dict() == before
    with pytest.raises(Exception):
        req.input = "mutated"  # type: ignore[misc]


def test_json_serialization_and_schema():
    ctx = ContextBuilder().build(_request())
    raw = ctx.to_canonical_dict()
    assert raw["schema_family"] == "cora.conversation.contracts"
    assert raw["schema_version"] == 1
    assert raw["kind"] == "ConversationContext"
    again = validate_context(raw)
    assert again.request_id == ctx.request_id
    assert again.sealed is True


def test_stub_providers_injectable():
    class CustomWorkspace(StubWorkspaceProvider):
        def fetch(self, request: ConversationRequest):
            return {
                "active": {"workspace_id": request.workspace_id, "name": "CUSTOM"},
                "memory": {"notes": ["injected"], "provider": "custom"},
            }

    ctx = ContextBuilder(workspace=CustomWorkspace()).build(_request())
    assert ctx.workspace["active"]["name"] == "CUSTOM"
    assert ctx.workspace["memory"]["notes"] == ["injected"]


def test_harness_uses_real_context_builder():
    h = ConversationHarness()
    assert isinstance(h.engine.context_builder, ContextBuilder)
    result = h.run_turn(
        {
            "request_id": "req-h-ctx",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "hello",
            "metadata": {"k": "v"},
        }
    )
    assert result.ok is True
    req = RequestValidator().validate(
        {
            "request_id": "req-h-ctx2",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "hello",
        }
    )
    ctx = h.engine.build_context(req)
    assert ctx.sealed is True
    assert ctx.conversation["memory"]["provider"] == "stub"


def test_context_builder_no_integrations():
    forbidden = {
        "github",
        "discord",
        "n8n",
        "electron",
        "react",
        "persona",
        "avatar",
        "planner",
        "openai",
        "httpx",
        "requests",
    }
    for path in CB_DIR.glob("*.py"):
        if path.name not in {"context_builder.py", "context_providers.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    low = alias.name.lower()
                    for bad in forbidden:
                        assert bad not in low.split(".")


def test_builder_does_not_decide():
    src = (CB_DIR / "context_builder.py").read_text(encoding="utf-8").lower()
    assert "decisionengine" not in src.replace("_", "")
    assert "planner" not in src
    assert "llm" not in src
