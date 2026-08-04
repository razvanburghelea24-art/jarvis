"""TDD — Railway Adapter (DispatchRequest → AdapterResult · mock · infra strict)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.adapters import (
    AdapterStatus,
    MockRailwayTransport,
    RailwayAdapter,
)
from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    DecisionEngine,
    RequestValidator,
    reset_conversation_event_journal_for_tests,
    reset_conversation_memory_for_tests,
)
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchOutcome,
    DispatchRequest,
    Dispatcher,
)
from src.jarvis.cora_foundation.planner import PlannerRouter
from src.jarvis.cora_foundation.tool_routing import ToolRouter


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _req(
    tool: str,
    *,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
) -> DispatchRequest:
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_rw",
        tool=tool,
        capability="railway.deploy",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=(
            {"project_id": "proj_1", "service_id": "svc_web"}
            if payload is None
            else payload
        ),
        metadata={"test": True},
    )


def test_project_status():
    r = RailwayAdapter().execute(
        _req(
            "Railway.project_status",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"project_id": "proj_1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.adapter == "railway"
    assert r.operation == "project_status"
    assert r.metadata.get("live") is False


def test_service_status():
    r = RailwayAdapter().execute(
        _req("Railway.service_status", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "service_status"


def test_deploy():
    r = RailwayAdapter().execute(_req("Railway.deploy"))
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "deploy"
    assert r.external_id


def test_restart_service():
    r = RailwayAdapter().execute(_req("Railway.restart_service"))
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "restart_service"


def test_approval_missing_deny():
    r = RailwayAdapter().execute(
        _req("Railway.deploy", approval=ApprovalState.PENDING)
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "DENY"


def test_missing_project():
    r = RailwayAdapter().execute(
        _req(
            "Railway.project_status",
            approval=ApprovalState.NOT_REQUIRED,
            payload={},
        )
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_PROJECT"


def test_missing_service():
    r = RailwayAdapter().execute(
        _req("Railway.deploy", payload={"project_id": "proj_1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_SERVICE"


def test_unsupported_operation():
    r = RailwayAdapter().execute(
        _req("Railway.destroy_cluster", payload={"project_id": "proj_1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "UNSUPPORTED_OPERATION"


def test_invalid_dispatch_request():
    r = RailwayAdapter().execute(None)  # type: ignore[arg-type]
    assert r.error == "INVALID_DISPATCH_REQUEST"
    r2 = RailwayAdapter().execute({"tool": "Railway.deploy"})  # type: ignore[arg-type]
    assert r2.error == "INVALID_DISPATCH_REQUEST"
    r3 = RailwayAdapter().execute(
        _req("GitHub.create_pr", payload={"project_id": "p", "service_id": "s"})
    )
    assert r3.error == "INVALID_DISPATCH_REQUEST"


def test_json_immutable():
    r = RailwayAdapter().execute(
        _req(
            "Railway.environment_info",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"project_id": "proj_1"},
        )
    )
    raw = r.to_canonical_dict()
    assert raw["schema_family"] == "cora.adapter.contracts"
    assert raw["adapter"] == "railway"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        r.status = AdapterStatus.FAILED  # type: ignore[misc]


def test_harness_dispatcher_to_railway_adapter():
    req = RequestValidator().validate(
        {
            "request_id": "req-rw-harness",
            "session_id": "sess-rw",
            "workspace_id": "ws",
            "input": "Deploy pe Railway pentru staging",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    rw_reqs = [r for r in batch.requests if r.tool.startswith("Railway.")]
    assert rw_reqs
    base = rw_reqs[0]
    enriched = DispatchRequest(
        dispatch_id=base.dispatch_id,
        plan_id=base.plan_id,
        tool=base.tool,
        capability=base.capability,
        execution_mode=base.execution_mode,
        approval_state=base.approval_state,
        payload={"project_id": "nymods-prod", "service_id": "cora-api"},
        metadata=dict(base.metadata),
        timestamp=base.timestamp,
    )
    result = RailwayAdapter(MockRailwayTransport()).execute(enriched)
    assert result.status == AdapterStatus.SUCCESS
    assert result.operation == "deploy"
    assert result.metadata.get("live") is False
