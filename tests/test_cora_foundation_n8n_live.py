"""TDD — n8n LIVE (phased · Gateway-gated · stub HTTP · READ before EXECUTE)."""

from __future__ import annotations

from typing import Any

from src.jarvis.cora_foundation.adapters import AdapterStatus, N8NAdapter
from src.jarvis.cora_foundation.adapters.n8n.live_transport import LiveN8NTransport
from src.jarvis.cora_foundation.adapters.n8n.path import execute_n8n_gated
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchRequest,
)
from src.jarvis.cora_foundation.live_gateway import (
    ExecutionMode,
    GatewayContext,
    LiveExecutionGateway,
)


def _req(
    tool: str,
    *,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
    capability: str | None = None,
) -> DispatchRequest:
    write_tools = {
        "n8n.execute_workflow",
        "n8n.activate_workflow",
        "n8n.deactivate_workflow",
        "n8n.cancel_execution",
    }
    is_write = tool in write_tools
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_n8n_live",
        tool=tool,
        capability=capability or ("n8n.execute" if is_write else "n8n.read"),
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload={"workflow_id": "wf_1"} if payload is None else payload,
        metadata={"test": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_n8n",
        workspace_id="ws_n8n",
        session_valid=True,
        workspace_active=True,
        mode=ExecutionMode.LIVE,
        rate_limit_ok=True,
        audit_available=True,
    )
    base.update(kwargs)
    return GatewayContext(**base)


def _stub(responses: dict[str, tuple[int, Any]]):
    def http(method: str, url: str, headers, body):
        key_hdr = str((headers or {}).get("X-N8N-API-KEY", ""))
        if "invalid-token" in key_hdr:
            return 401, {"message": "unauthorized"}
        for key, val in responses.items():
            m, path = key.split(" ", 1)
            if method == m and path in url:
                return val
        return 404, {"message": "not_found"}

    return http


def _live(phase: int, http, token: str = "ok-token") -> LiveN8NTransport:
    return LiveN8NTransport(token=token, phase=phase, http=http)


def test_workflow_status_read_phase1():
    http = _stub(
        {"GET /workflows/wf_1": (200, {"id": "wf_1", "active": True})}
    )
    r = N8NAdapter(_live(1, http)).execute(
        _req("n8n.workflow_status", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.metadata.get("live") is True


def test_phase1_locks_execute():
    r = N8NAdapter(_live(1, _stub({}))).execute(_req("n8n.execute_workflow"))
    assert r.error == "PHASE_LOCKED"


def test_activate_phase2():
    http = _stub(
        {"POST /workflows/wf_1/activate": (200, {"id": "wf_1", "active": True})}
    )
    r = N8NAdapter(_live(2, http)).execute(_req("n8n.activate_workflow"))
    assert r.status == AdapterStatus.SUCCESS


def test_phase2_locks_execute():
    r = N8NAdapter(_live(2, _stub({}))).execute(_req("n8n.execute_workflow"))
    assert r.error == "PHASE_LOCKED"


def test_execute_phase3():
    http = _stub(
        {
            "POST /workflows/wf_1/run": (
                200,
                {"id": "ex_9", "execution_id": "ex_9"},
            )
        }
    )
    r = N8NAdapter(_live(3, http)).execute(_req("n8n.execute_workflow"))
    assert r.status == AdapterStatus.SUCCESS
    assert r.external_id == "ex_9"


def test_gated_safe_mode_deny():
    out = execute_n8n_gated(
        _req("n8n.execute_workflow"),
        _ctx(safe_mode=True),
        transport=_live(3, _stub({})),
    )
    assert out.gateway.reason == "SAFE_MODE_WRITE_BLOCKED"
    assert out.adapter is None


def test_gated_allow_read():
    audits: list = []
    http = _stub({"GET /workflows": (200, {"data": [{"id": "wf_1"}]})})
    out = execute_n8n_gated(
        _req(
            "n8n.list_workflows",
            approval=ApprovalState.NOT_REQUIRED,
            payload={},
        ),
        _ctx(),
        gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d) or True),
        transport=_live(1, http),
    )
    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.status == AdapterStatus.SUCCESS
    assert audits
