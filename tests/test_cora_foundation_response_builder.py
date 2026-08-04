"""TDD — ResponseBuilder (Decision+Context → ConversationResponse · Harness).

Deterministic templates only. No LLM / Planner / Gateway / Electron / Persona.
No Memory writes · no State emit · no Streaming.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    ConversationHarness,
    DecisionEngine,
    LifecyclePhase,
    RequestValidator,
    ResponseBuilder,
    validate_response,
    reset_conversation_event_journal_for_tests,
)

RB_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "response_builder.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _triple(**req_overrides):
    raw = {
        "request_id": "req-rb-1",
        "session_id": "sess-rb",
        "workspace_id": "ws-nymods",
        "input": "salut",
        "barge_in": False,
        "metadata": {},
    }
    raw.update(req_overrides)
    req = RequestValidator().validate(raw)
    ctx = ContextBuilder().build(req)
    decision = DecisionEngine().decide(req, ctx)
    return req, ctx, decision


def test_respond_placeholder_response():
    req, ctx, decision = _triple(input="status pe NyMods")
    assert decision.tool_intent["label"] == "Respond"
    resp = ResponseBuilder().build(req, ctx, decision)
    assert resp.request_id == req.request_id
    assert resp.decision_id == decision.decision_id
    assert resp.phase == LifecyclePhase.COMPLETED
    assert resp.incomplete is False
    assert resp.metadata["response_mode"] == "placeholder"
    assert resp.metadata["label"] == "Respond"
    assert "[placeholder]" in resp.text.lower() or "placeholder" in resp.text.lower()
    assert resp.text.strip() != ""


def test_ask_clarification_response():
    req, ctx, decision = _triple(input="  ")
    assert decision.tool_intent["label"] == "AskClarification"
    resp = ResponseBuilder().build(req, ctx, decision)
    assert resp.metadata["response_mode"] == "clarification"
    assert resp.metadata["label"] == "AskClarification"
    assert "clarif" in resp.text.lower() or "detail" in resp.text.lower() or "rephrase" in resp.text.lower()
    assert resp.phase == LifecyclePhase.COMPLETED


def test_needs_review_response():
    req, ctx, decision = _triple(input="", metadata={"attachments": ["a.png"]})
    assert decision.tool_intent["label"] == "NeedsReview"
    resp = ResponseBuilder().build(req, ctx, decision)
    assert resp.metadata["response_mode"] == "review"
    assert resp.metadata["label"] == "NeedsReview"
    assert "attach" in resp.text.lower() or "review" in resp.text.lower()
    assert resp.phase == LifecyclePhase.COMPLETED


def test_refuse_response():
    req, ctx, decision = _triple(input="x", metadata={"content_kind": "binary_blob"})
    assert decision.tool_intent["label"] == "Refuse"
    resp = ResponseBuilder().build(req, ctx, decision)
    assert resp.metadata["response_mode"] == "refuse"
    assert resp.metadata["label"] == "Refuse"
    assert "cannot" in resp.text.lower() or "refuse" in resp.text.lower() or "unsupported" in resp.text.lower()
    assert resp.phase == LifecyclePhase.COMPLETED


def test_contracts_v1_json_immutable():
    req, ctx, decision = _triple()
    resp = ResponseBuilder().build(req, ctx, decision)
    raw = resp.to_canonical_dict()
    assert raw["schema_family"] == "cora.conversation.contracts"
    assert raw["schema_version"] == 1
    assert raw["kind"] == "ConversationResponse"
    again = validate_response(raw)
    assert again.response_id == resp.response_id
    assert again.text == resp.text
    # recommended extras live in metadata (contracts.v1 frozen)
    assert "response_mode" in again.metadata
    assert "actions" in again.metadata
    assert "warnings" in again.metadata
    assert "tool_intent" in again.metadata
    with pytest.raises(Exception):
        resp.text = "mutated"  # type: ignore[misc]


def test_harness_pass():
    h = ConversationHarness()
    assert isinstance(h.engine.response_builder, ResponseBuilder)
    result = h.run_turn(
        {
            "request_id": "req-h-rb",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "hello",
        }
    )
    assert result.ok is True
    assert result.response is not None
    assert result.response.metadata.get("label") == "Respond"
    assert result.response.metadata.get("response_mode") == "placeholder"
    assert result.response.text.strip() != ""


def test_no_external_integrations():
    forbidden = {
        "gateway",
        "planner",
        "openai",
        "anthropic",
        "electron",
        "react",
        "persona",
        "avatar",
        "camera",
        "httpx",
        "requests",
        "discord",
        "memory",
        "snapshot",
        "state_emitter",
    }
    tree = ast.parse(RB_PATH.read_text(encoding="utf-8"))
    src = RB_PATH.read_text(encoding="utf-8").lower()
    body = src.split('"""', 2)[-1] if '"""' in src else src
    assert "stream_" not in body
    assert ".stream(" not in body
    assert "persona.set" not in body
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
