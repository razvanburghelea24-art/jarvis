"""Conversation Engine Skeleton — structure only, zero business logic."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ConversationEngine,
    ContextBuilder,
    DecisionEngine,
    RequestValidator,
    ResponseBuilder,
    SkeletonNotImplemented,
    StateEmitter,
)

ENGINE_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
)


def test_skeleton_flag_and_components():
    engine = ConversationEngine()
    assert engine.SKELETON is True
    assert isinstance(engine.validator, RequestValidator)
    assert isinstance(engine.context_builder, ContextBuilder)
    assert isinstance(engine.decision_engine, DecisionEngine)
    assert isinstance(engine.response_builder, ResponseBuilder)
    assert isinstance(engine.state_emitter, StateEmitter)


def test_pipeline_methods_exist():
    engine = ConversationEngine()
    for name in ("submit", "validate", "build_context", "decide", "emit_state", "emit_response"):
        assert callable(getattr(engine, name))


def test_each_step_raises_skeleton_not_implemented():
    engine = ConversationEngine()
    req = {
        "request_id": "r",
        "session_id": "s",
        "workspace_id": "w",
        "input": "x",
    }
    validated = engine.validate(req)
    ctx = engine.build_context(validated)
    decision = engine.decide(validated, ctx)
    final = engine.emit_state(validated, decision)
    assert final.presentation.value in {"Thinking", "Completed", "WaitingOwner"}
    with pytest.raises(SkeletonNotImplemented, match="ResponseBuilder"):
        engine.emit_response(validated, ctx, decision)
    with pytest.raises(SkeletonNotImplemented, match="ResponseBuilder"):
        engine.submit(req)


def test_component_methods_are_stubs():
    with pytest.raises(SkeletonNotImplemented):
        ResponseBuilder().build("x", "y", "z")  # type: ignore[arg-type]



def test_no_desktop_ui_imports_in_engine():
    forbidden = {
        "electron",
        "react",
        "persona",
        "avatar",
        "camera",
        "lighting",
        "fx",
        "blender",
        "metahuman",
        "openai",
        "anthropic",
        "httpx",
        "requests",
        "discord",
    }
    for path in ENGINE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    low = alias.name.lower()
                    for bad in forbidden:
                        assert bad not in low.split("."), f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if mod.startswith(".") or "cora_foundation.conversation" in mod:
                    continue
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"


def test_submit_source_documents_pipeline_order():
    src = inspect.getsource(ConversationEngine.submit)
    # Strip docstring — may mention deferred Streaming without implementing it
    body = src.split('"""', 2)[-1] if '"""' in src else src
    assert "self.validate" in body
    assert "self.build_context" in body
    assert "self.decide" in body
    assert "self.emit_state" in body
    assert "self.emit_response" in body
    assert body.index("self.validate") < body.index("self.build_context")
    assert body.index("self.build_context") < body.index("self.decide")
    assert body.index("self.decide") < body.index("self.emit_state")
    assert body.index("self.emit_state") < body.index("self.emit_response")
    # No streaming API in the callable body yet
    assert "stream_" not in body.lower()
    assert ".stream(" not in body.lower()
