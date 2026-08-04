"""Beta 1.0 — Conversation contracts v1 (schema freeze: types + validation only)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    SCHEMA_FAMILY,
    SCHEMA_ID,
    SCHEMA_VERSION,
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    ConversationState,
    DecisionKind,
    ErrorClass,
    LifecyclePhase,
    PresentationHint,
    ValidationError,
    from_canonical_json,
    to_canonical_json,
    validate,
    validate_decision,
    validate_request,
    validate_response,
    validate_state,
)

CONV_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
)


def _envelope(kind: str, **payload):
    return {
        "schema_family": SCHEMA_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        **payload,
    }


def test_schema_identity_frozen():
    assert SCHEMA_FAMILY == "cora.conversation.contracts"
    assert SCHEMA_VERSION == 1
    assert SCHEMA_ID == "cora.conversation.contracts.v1"


def test_request_validates_and_roundtrips():
    obj = validate_request(
        _envelope(
            "ConversationRequest",
            request_id="req-1",
            session_id="sess-1",
            workspace_id="ws-nymods",
            input="status pe NyMods",
            barge_in=False,
        )
    )
    assert isinstance(obj, ConversationRequest)
    assert obj.workspace_id == "ws-nymods"
    raw = to_canonical_json(obj)
    again = from_canonical_json(raw)
    assert isinstance(again, ConversationRequest)
    assert again.to_canonical_dict() == obj.to_canonical_dict()
    parsed = json.loads(raw)
    assert parsed["schema_family"] == SCHEMA_FAMILY
    assert parsed["schema_version"] == 1
    assert parsed["kind"] == "ConversationRequest"


def test_request_rejects_missing_workspace():
    with pytest.raises(ValidationError, match="workspace_id"):
        validate_request(
            _envelope(
                "ConversationRequest",
                request_id="req-1",
                session_id="sess-1",
                workspace_id="",
                input="hi",
            )
        )


def test_request_rejects_bad_family():
    with pytest.raises(ValidationError):
        validate(
            {
                "schema_family": "other.family",
                "schema_version": 1,
                "kind": "ConversationRequest",
                "request_id": "r",
                "session_id": "s",
                "workspace_id": "w",
                "input": "x",
            }
        )


def test_contracts_are_immutable():
    req = validate_request(
        _envelope(
            "ConversationRequest",
            request_id="req-1",
            session_id="sess-1",
            workspace_id="ws-1",
            input="hello",
            metadata={"a": 1},
        )
    )
    with pytest.raises(Exception):
        req.request_id = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        req.metadata["x"] = 1  # type: ignore[index]

    ctx = ConversationContext(
        request_id="r",
        session_id="s",
        workspace_id="w",
        conversation={"turns": []},
        sealed=True,
    )
    with pytest.raises(TypeError):
        ctx.conversation["turns"] = [1]  # type: ignore[index]


def test_all_five_contracts_roundtrip():
    ctx = validate(
        _envelope(
            "ConversationContext",
            request_id="req-1",
            session_id="sess-1",
            workspace_id="ws-nymods",
            conversation={"turns": 2},
            workspace={"name": "NyMods"},
            core={"owner": "bos"},
            runtime={"e_stop": False},
            sealed=True,
        )
    )
    assert isinstance(ctx, ConversationContext)

    decision = validate(
        _envelope(
            "ConversationDecision",
            decision_id="dec-1",
            request_id="req-1",
            decision_kind="tool",
            workspace_id="ws-nymods",
            planner_ref="plan-9",
            tool_intent={"capability": "GitHub.status"},
            reason="owner asked status",
        )
    )
    assert isinstance(decision, ConversationDecision)
    assert decision.kind == DecisionKind.TOOL

    answer = validate_decision(
        _envelope(
            "ConversationDecision",
            decision_id="dec-2",
            request_id="req-1",
            decision_kind="answer",
            workspace_id="ws-nymods",
            reason="direct reply",
        )
    )
    assert answer.kind == DecisionKind.ANSWER

    response = validate_response(
        _envelope(
            "ConversationResponse",
            response_id="resp-1",
            request_id="req-1",
            decision_id="dec-2",
            phase="Streaming",
            text="NyMods e online.",
            incomplete=False,
            citations=["runtime"],
        )
    )
    assert isinstance(response, ConversationResponse)
    assert response.phase == LifecyclePhase.STREAMING

    state = validate_state(
        _envelope(
            "ConversationState",
            session_id="sess-1",
            request_id="req-1",
            workspace_id="ws-nymods",
            lifecycle="Streaming",
            presentation="Speaking",
            error_class=None,
        )
    )
    assert isinstance(state, ConversationState)
    assert state.presentation == PresentationHint.SPEAKING

    for obj in (ctx, decision, answer, response, state):
        restored = from_canonical_json(to_canonical_json(obj))
        assert restored.to_canonical_dict() == obj.to_canonical_dict()


def test_tool_decision_requires_capability():
    with pytest.raises(ValidationError, match="capability"):
        validate_decision(
            _envelope(
                "ConversationDecision",
                decision_id="dec-1",
                request_id="req-1",
                decision_kind="tool",
                workspace_id="ws-1",
                tool_intent={},
            )
        )


def test_state_error_class():
    state = validate_state(
        _envelope(
            "ConversationState",
            session_id="sess-1",
            request_id=None,
            workspace_id="ws-1",
            lifecycle="Completed",
            presentation="Waiting",
            error_class="workspace_missing",
        )
    )
    assert state.error_class == ErrorClass.WORKSPACE_MISSING


def test_no_desktop_persona_avatar_imports():
    """DoD: conversation package must not know Electron/React/Persona/Avatar."""
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
        "discord",
        "openai",
        "anthropic",
        "httpx",
        "requests",
    }
    for path in CONV_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    low = alias.name.lower()
                    for bad in forbidden:
                        assert bad not in low.split("."), f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if mod.startswith("src.jarvis.cora_foundation.conversation") or mod.startswith("."):
                    continue
                # conversation may not import sibling foundation engines either in this freeze
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"


def test_package_has_no_engine_modules():
    """Contracts package stays types-only; Engine lives under conversation/engine/."""
    contracts_dir = CONV_DIR / "contracts"
    names = {p.name for p in contracts_dir.rglob("*.py")}
    for banned in ("engine.py", "planner.py", "gateway.py", "llm.py"):
        assert banned not in names
