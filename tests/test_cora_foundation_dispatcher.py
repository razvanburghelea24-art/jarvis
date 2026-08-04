"""TDD — Dispatcher (ToolPlan → DispatchRequest · never execute adapters)."""

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
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchOutcome,
    Dispatcher,
)
from src.jarvis.cora_foundation.llm import ModelRouter, routing_test_registry
from src.jarvis.cora_foundation.planner import PlannerRouter
from src.jarvis.cora_foundation.tool_routing import ExecutionMode, ToolPlan, ToolRisk, ToolRouter
from src.jarvis.cora_foundation.workspace import StubWorkspaceStore, WorkspaceEngine


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _tool_plan(text: str) -> ToolPlan:
    req = RequestValidator().validate(
        {
            "request_id": "req-disp-1",
            "session_id": "sess-disp",
            "workspace_id": "ws",
            "input": text,
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    return ToolRouter().route(planner, req)


def _manual_plan(*, tools: tuple[str, ...], approval: bool = True) -> ToolPlan:
    return ToolPlan(
        plan_id="tplan_manual",
        request_id="req-manual",
        planner_decision_id="pdec_manual",
        required_tools=tools,
        required_capabilities=(),
        approval_required=approval,
        execution_mode=ExecutionMode.NONE,
        risk=ToolRisk.HIGH if tools else ToolRisk.NONE,
        metadata={"test": True},
    )


def test_github_dispatch_request():
    plan = _tool_plan("Creează un PR pe GitHub pentru overlay")
    result = Dispatcher().dispatch(plan, approval_granted=True)
    assert result.outcome == DispatchOutcome.READY
    assert len(result.requests) >= 1
    assert result.requests[0].tool == "GitHub.create_pr"
    assert result.requests[0].capability == "github.write"
    assert result.requests[0].approval_state == ApprovalState.GRANTED
    assert result.requests[0].execution_mode.value == "none"
    assert result.metadata["adapter_invoked"] is False


def test_discord_dispatch_request():
    plan = _tool_plan("Fă un plan și trimite anunț pe Discord")
    result = Dispatcher().dispatch(plan, approval_granted=True)
    assert any(r.tool == "Discord.send" for r in result.requests)
    assert result.outcome == DispatchOutcome.READY


def test_framework_dispatch_request():
    plan = _tool_plan("Construiește și rulează framework pipeline")
    result = Dispatcher().dispatch(plan, approval_granted=True)
    assert any(r.tool == "Framework.run" for r in result.requests) or (
        not plan.empty and result.outcome in {DispatchOutcome.READY, DispatchOutcome.PARTIAL}
    )


def test_railway_dispatch_request():
    plan = _tool_plan("Deploy pe Railway pentru staging")
    result = Dispatcher().dispatch(plan, approval_granted=True)
    assert any(r.tool == "Railway.deploy" for r in result.requests)
    assert result.outcome == DispatchOutcome.READY


def test_empty_plan_no_dispatch():
    plan = _tool_plan("Ce este Conversation Engine?")
    result = Dispatcher().dispatch(plan)
    assert result.outcome == DispatchOutcome.EMPTY
    assert result.requests == ()
    assert result.empty is True


def test_approval_missing_deny():
    plan = _tool_plan("Creează un PR pe GitHub")
    assert plan.approval_required is True
    result = Dispatcher().dispatch(plan, approval_granted=False)
    assert result.outcome == DispatchOutcome.DENY
    assert result.requests == ()
    assert result.errors[0]["code"] == "DENY"


def test_unknown_tool_unsupported():
    plan = _manual_plan(tools=("Alien.teleport",), approval=False)
    result = Dispatcher().dispatch(plan)
    assert result.outcome == DispatchOutcome.UNSUPPORTED_TOOL
    assert result.requests == ()
    assert result.errors[0]["code"] == "UNSUPPORTED_TOOL"
    assert result.errors[0]["tool"] == "Alien.teleport"


def test_multiple_tools_dispatch():
    plan = _tool_plan("Deploy pe Railway și creează un PR pe GitHub")
    result = Dispatcher().dispatch(plan, approval_granted=True)
    tools = {r.tool for r in result.requests}
    assert "Railway.deploy" in tools
    assert "GitHub.create_pr" in tools
    assert len(result.requests) >= 2


def test_json_immutable():
    plan = _manual_plan(tools=("Discord.send",), approval=False)
    result = Dispatcher().dispatch(plan)
    req = result.requests[0]
    raw = req.to_canonical_dict()
    assert raw["schema_family"] == "cora.dispatch.contracts"
    assert raw["kind"] == "DispatchRequest"
    assert json.dumps(raw)
    assert json.dumps(result.to_canonical_dict())
    with pytest.raises(Exception):
        req.tool = "hacked"  # type: ignore[misc]
    with pytest.raises(Exception):
        result.outcome = DispatchOutcome.DENY  # type: ignore[misc]


def test_does_not_mutate_tool_plan():
    plan = _manual_plan(tools=("GitHub.create_pr",), approval=True)
    before = plan.to_canonical_dict()
    Dispatcher().dispatch(plan, approval_granted=True)
    assert plan.to_canonical_dict() == before


def test_harness_wired_pipeline_includes_dispatch():
    p = WiredConversationPipeline(
        workspace=WorkspaceEngine(StubWorkspaceStore()),
        router=ModelRouter(routing_test_registry()),
    )
    result = p.run(
        {
            "request_id": "req-wire-disp",
            "session_id": "sess-wire-disp",
            "workspace_id": "ws",
            "input": "Creează un PR pe GitHub",
        },
        stream=False,
    )
    assert result.ok is True
    assert result.tool_plan is not None
    assert result.dispatch is not None
    # default: approval not granted → DENY (safe gate)
    assert result.dispatch.outcome == DispatchOutcome.DENY
    assert result.to_dict()["dispatch"]["outcome"] == "deny"
    assert result.to_dict()["dispatch"]["requests"] == []
