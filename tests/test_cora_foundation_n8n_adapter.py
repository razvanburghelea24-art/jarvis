"""TDD — n8n Adapter (DispatchRequest → AdapterResult · mock · last Integration Layer piece)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.adapters import AdapterStatus, MockN8NTransport, N8NAdapter
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
        plan_id="tplan_n8n",
        tool=tool,
        capability="n8n.execute",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload={"workflow_id": "wf_1"} if payload is None else payload,
        metadata={"test": True},
    )


def test_workflow_status():
    r = N8NAdapter().execute(
        _req("n8n.workflow_status", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.adapter == "n8n"
    assert r.operation == "workflow_status"
    assert r.metadata.get("live") is False


def test_list_workflows():
    r = N8NAdapter().execute(
        _req("n8n.list_workflows", approval=ApprovalState.NOT_REQUIRED, payload={})
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "list_workflows"


def test_execute_workflow():
    r = N8NAdapter().execute(_req("n8n.execute_workflow"))
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "execute_workflow"
    assert r.external_id


def test_cancel_execution():
    r = N8NAdapter().execute(
        _req(
            "n8n.cancel_execution",
            payload={"workflow_id": "wf_1", "execution_id": "ex_99"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "cancel_execution"


def test_approval_missing_deny():
    r = N8NAdapter().execute(
        _req("n8n.execute_workflow", approval=ApprovalState.PENDING)
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "DENY"


def test_missing_workflow():
    r = N8NAdapter().execute(
        _req("n8n.execute_workflow", payload={})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_WORKFLOW"


def test_unsupported_operation():
    r = N8NAdapter().execute(
        _req("n8n.delete_all", payload={"workflow_id": "wf_1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "UNSUPPORTED_OPERATION"


def test_invalid_dispatch_request():
    r = N8NAdapter().execute(None)  # type: ignore[arg-type]
    assert r.error == "INVALID_DISPATCH_REQUEST"
    r2 = N8NAdapter().execute({"tool": "n8n.execute_workflow"})  # type: ignore[arg-type]
    assert r2.error == "INVALID_DISPATCH_REQUEST"
    r3 = N8NAdapter().execute(
        _req("Railway.deploy", payload={"workflow_id": "wf_1"})
    )
    assert r3.error == "INVALID_DISPATCH_REQUEST"


def test_json_immutable():
    r = N8NAdapter().execute(
        _req("n8n.workflow_info", approval=ApprovalState.NOT_REQUIRED)
    )
    raw = r.to_canonical_dict()
    assert raw["schema_family"] == "cora.adapter.contracts"
    assert raw["adapter"] == "n8n"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        r.status = AdapterStatus.FAILED  # type: ignore[misc]


def test_harness_dispatcher_to_n8n_adapter():
    req = RequestValidator().validate(
        {
            "request_id": "req-n8n-harness",
            "session_id": "sess-n8n",
            "workspace_id": "ws",
            "input": "Fă un plan și rulează workflow n8n pentru notify",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    n8n_reqs = [r for r in batch.requests if r.tool.startswith("n8n.")]
    assert n8n_reqs
    base = n8n_reqs[0]
    enriched = DispatchRequest(
        dispatch_id=base.dispatch_id,
        plan_id=base.plan_id,
        tool=base.tool,
        capability=base.capability,
        execution_mode=base.execution_mode,
        approval_state=base.approval_state,
        payload={"workflow_id": "wf_notify"},
        metadata=dict(base.metadata),
        timestamp=base.timestamp,
    )
    result = N8NAdapter(MockN8NTransport()).execute(enriched)
    assert result.status == AdapterStatus.SUCCESS
    assert result.operation == "execute_workflow"
    assert result.metadata.get("live") is False
