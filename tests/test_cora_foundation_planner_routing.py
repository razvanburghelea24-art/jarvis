"""TDD — Planner Routing (PlannerDecision only · never execute)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    DecisionEngine,
    RequestValidator,
    WiredConversationPipeline,
    reset_conversation_event_journal_for_tests,
    reset_conversation_memory_for_tests,
)
from src.jarvis.cora_foundation.llm import ModelRouter, routing_test_registry
from src.jarvis.cora_foundation.planner import (
    PlannerDecision,
    PlannerRisk,
    PlannerRoute,
    PlannerRouter,
)
from src.jarvis.cora_foundation.workspace import StubWorkspaceStore, WorkspaceEngine


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _triple(text: str, **meta):
    req = RequestValidator().validate(
        {
            "request_id": "req-pr-1",
            "session_id": "sess-pr",
            "workspace_id": "ws-nymods",
            "input": text,
            "metadata": meta or {},
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    return req, ctx, dec


def test_simple_question_direct_response():
    req, ctx, dec = _triple("Ce este NyMods?")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is False
    assert pd.route == PlannerRoute.DIRECT_RESPONSE
    assert pd.estimated_steps == 0
    assert pd.risk == PlannerRisk.NONE


def test_explain_direct_response():
    req, ctx, dec = _triple("Explică ce face Conversation Engine")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is False
    assert pd.route == PlannerRoute.DIRECT_RESPONSE


def test_build_request_requires_plan():
    req, ctx, dec = _triple("Construiește un modul de export pentru overlay")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is True
    assert pd.route == PlannerRoute.CREATE_PLAN
    assert pd.estimated_steps >= 3
    assert pd.estimated_cost > 0
    assert pd.estimated_duration_sec > 0
    assert len(pd.required_capabilities) >= 1


def test_analyze_project_requires_plan():
    req, ctx, dec = _triple("Analizează proiectul NyMods și propune îmbunătățiri")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is True
    assert pd.route == PlannerRoute.CREATE_PLAN


def test_compare_variants_requires_plan():
    req, ctx, dec = _triple("Compară 5 variante de arhitectură pentru Router")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is True
    assert pd.estimated_steps >= 5


def test_explicit_plan_request():
    req, ctx, dec = _triple("Fă un plan pentru migrarea la Beta")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is True
    assert pd.route == PlannerRoute.CREATE_PLAN


def test_existing_plan_route():
    ws = WorkspaceEngine(StubWorkspaceStore())
    ws.switch("sess-pr", "ws-nymods")
    ws.set_plan("sess-pr", "plan-alpha-migrate")
    req, ctx, dec = _triple("continuă")
    # rebind session
    req = RequestValidator().validate(
        {
            "request_id": "req-pr-ex",
            "session_id": "sess-pr",
            "workspace_id": "ws-nymods",
            "input": "continuă",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    pd = PlannerRouter().route(req, ctx, dec, workspace=ws)
    assert pd.route == PlannerRoute.EXISTING_PLAN
    assert pd.required is True
    assert pd.metadata.get("active_plan") == "plan-alpha-migrate"


def test_risk_and_capabilities_estimated():
    req, ctx, dec = _triple("Deploy pe Railway și deschide un PR pe GitHub")
    pd = PlannerRouter().route(req, ctx, dec)
    assert pd.required is True
    assert pd.risk == PlannerRisk.HIGH
    assert "deploy" in pd.required_capabilities
    assert "github" in pd.required_capabilities
    assert pd.approval_required is True


def test_json_immutable():
    req, ctx, dec = _triple("salut")
    pd = PlannerRouter().route(req, ctx, dec)
    raw = pd.to_canonical_dict()
    assert raw["schema_family"] == "cora.planner.routing.contracts"
    assert raw["kind"] == "PlannerDecision"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        pd.required = True  # type: ignore[misc]


def test_harness_wired_pipeline_includes_planner():
    reset_conversation_memory_for_tests()
    p = WiredConversationPipeline(
        workspace=WorkspaceEngine(StubWorkspaceStore()),
        router=ModelRouter(routing_test_registry()),
    )
    result = p.run(
        {
            "request_id": "req-wire-pr",
            "session_id": "sess-wire",
            "workspace_id": "ws",
            "input": "Construiește un endpoint de health",
        },
        stream=False,
    )
    assert result.ok is True
    assert result.planner is not None
    assert result.planner.required is True
    assert result.planner.route == PlannerRoute.CREATE_PLAN
    assert result.to_dict()["planner"]["required"] is True
