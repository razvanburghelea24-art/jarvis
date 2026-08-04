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
    with pytest.raises(SkeletonNotImplemented, match="RequestValidator"):
        engine.validate({"request_id": "r", "session_id": "s", "workspace_id": "w", "input": "x"})

    # submit stops at first step
    with pytest.raises(SkeletonNotImplemented, match="RequestValidator"):
        engine.submit({"request_id": "r", "session_id": "s", "workspace_id": "w", "input": "x"})


def test_component_methods_are_stubs():
    stubs = [
        (RequestValidator().validate, ("x",)),
        (ContextBuilder().build, ("x",)),
        (DecisionEngine().decide, ("x", "y")),
        (ResponseBuilder().build, ("x", "y", "z")),
        (StateEmitter().emit, ("x",), {"presentation": "Idle"}),
    ]
    for item in stubs:
        fn = item[0]
        args = item[1]
        kwargs = item[2] if len(item) > 2 else {}
        with pytest.raises(SkeletonNotImplemented):
            fn(*args, **kwargs)


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
    # Frozen order markers in spine
    assert "validate" in src
    assert "build_context" in src
    assert "decide" in src
    assert "emit_state" in src
    assert "emit_response" in src
    assert src.index("validate") < src.index("build_context")
    assert src.index("build_context") < src.index("decide")
    assert src.index("decide") < src.index("emit_state")
    assert src.index("emit_state") < src.index("emit_response")
    # Streaming must not sneak into skeleton submit
    assert "stream" not in src.lower()
