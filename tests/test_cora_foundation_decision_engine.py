"""TDD — DecisionEngine (deterministic rules only · Harness).

Context → ConversationDecision. No LLM / Planner / Gateway / Tools / Memory writes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    ConversationHarness,
    DecisionEngine,
    DecisionKind,
    RequestValidator,
    validate_decision,
    reset_conversation_event_journal_for_tests,
)

DE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "decision_engine.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _pair(**req_overrides):
    raw = {
        "request_id": "req-de-1",
        "session_id": "sess-de",
        "workspace_id": "ws-nymods",
        "input": "salut",
        "barge_in": False,
        "metadata": {},
    }
    raw.update(req_overrides)
    req = RequestValidator().validate(raw)
    ctx = ContextBuilder().build(req)
    return req, ctx


def _meta(decision):
    return dict(decision.tool_intent)


def test_empty_input_ask_clarification():
    req, ctx = _pair(input="   ")
    d = DecisionEngine().decide(req, ctx)
    assert d.kind == DecisionKind.CLARIFY
    m = _meta(d)
    assert m["label"] == "AskClarification"
    assert m["planner_required"] is False
    assert m["tool_required"] is False
    assert m["confidence"] >= 0.9


def test_normal_input_respond():
    req, ctx = _pair(input="cum stă NyMods?")
    d = DecisionEngine().decide(req, ctx)
    assert d.kind == DecisionKind.ANSWER
    m = _meta(d)
    assert m["label"] == "Respond"
    assert m["response_mode"] == "direct"
    assert m["planner_required"] is False
    assert m["tool_required"] is False
    assert 0.0 < m["confidence"] <= 1.0


def test_unsupported_kind_refuse():
    req, ctx = _pair(input="x", metadata={"content_kind": "binary_blob"})
    d = DecisionEngine().decide(req, ctx)
    assert d.kind == DecisionKind.REFUSE
    m = _meta(d)
    assert m["label"] == "Refuse"
    assert m["planner_required"] is False
    assert m["tool_required"] is False


def test_attachment_only_needs_review():
    req, ctx = _pair(input="", metadata={"attachments": ["file://a.png"]})
    d = DecisionEngine().decide(req, ctx)
    assert d.kind == DecisionKind.CLARIFY
    m = _meta(d)
    assert m["label"] == "NeedsReview"
    assert m["response_mode"] == "review"


def test_confidence_calculated():
    _, ctx = _pair(input="hello world")
    d = DecisionEngine().decide(_pair(input="hello world")[0], ctx)
    assert isinstance(_meta(d)["confidence"], float)


def test_json_valid_and_immutable():
    req, ctx = _pair()
    d = DecisionEngine().decide(req, ctx)
    raw = d.to_canonical_dict()
    assert raw["schema_family"] == "cora.conversation.contracts"
    assert raw["kind"] == "ConversationDecision"
    again = validate_decision(raw)
    assert again.request_id == d.request_id
    with pytest.raises(Exception):
        d.reason = "mutated"  # type: ignore[misc]


def test_never_sets_tool_or_planner_execute():
    req, ctx = _pair(input="deploy everything")
    d = DecisionEngine().decide(req, ctx)
    m = _meta(d)
    assert m["planner_required"] is False
    assert m["tool_required"] is False
    assert d.kind != DecisionKind.TOOL
    assert d.planner_ref is None


def test_harness_uses_real_decision_engine():
    h = ConversationHarness()
    assert isinstance(h.engine.decision_engine, DecisionEngine)
    result = h.run_turn(
        {
            "request_id": "req-h-de",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "status",
        }
    )
    assert result.ok is True
    req, ctx = _pair(request_id="req-h-de2", input="status")
    d = h.engine.decide(req, ctx)
    assert _meta(d)["label"] == "Respond"


def test_decision_engine_no_integrations():
    forbidden = {
        "gateway",
        "planner",
        "openai",
        "anthropic",
        "electron",
        "react",
        "persona",
        "avatar",
        "httpx",
        "discord",
        "github",
    }
    tree = ast.parse(DE_PATH.read_text(encoding="utf-8"))
    src = DE_PATH.read_text(encoding="utf-8").lower()
    # Callable body must not invoke planner
    body = src.split('"""', 2)[-1] if '"""' in src else src
    assert "planner.execute" not in body
    assert "import gateway" not in body
    assert "from" not in body or "gateway" not in [
        (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            for bad in forbidden:
                assert bad not in mod.split("."), mod
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name.lower().split(".")
