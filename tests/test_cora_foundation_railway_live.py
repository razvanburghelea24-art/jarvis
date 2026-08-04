"""TDD — Railway LIVE (phased · Gateway-gated · stub HTTP · READ before WRITE)."""

from __future__ import annotations

from typing import Any

from src.jarvis.cora_foundation.adapters import AdapterStatus, RailwayAdapter
from src.jarvis.cora_foundation.adapters.railway.live_transport import LiveRailwayTransport
from src.jarvis.cora_foundation.adapters.railway.path import execute_railway_gated
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
        "Railway.deploy",
        "Railway.restart_service",
        "Railway.rollback",
        "Railway.set_variable",
        "Railway.delete_variable",
    }
    is_write = tool in write_tools
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_rw_live",
        tool=tool,
        capability=capability or ("railway.deploy" if is_write else "railway.read"),
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=(
            {"project_id": "proj_1", "service_id": "svc_web"}
            if payload is None
            else payload
        ),
        metadata={"test": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_rw",
        workspace_id="ws_rw",
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
        auth = str((headers or {}).get("Authorization", ""))
        if "invalid-token" in auth:
            return 401, {"message": "unauthorized"}
        for key, val in responses.items():
            m, path = key.split(" ", 1)
            if method == m and path in url:
                return val
        return 404, {"message": "not_found"}

    return http


def _live(phase: int, http, token: str = "ok-token") -> LiveRailwayTransport:
    return LiveRailwayTransport(token=token, phase=phase, http=http)


def test_project_status_read_phase1():
    http = _stub({"GET /projects/proj_1": (200, {"id": "proj_1", "status": "healthy"})})
    r = RailwayAdapter(_live(1, http)).execute(
        _req(
            "Railway.project_status",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"project_id": "proj_1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.metadata.get("live") is True


def test_phase1_locks_deploy():
    r = RailwayAdapter(_live(1, _stub({}))).execute(_req("Railway.deploy"))
    assert r.error == "PHASE_LOCKED"


def test_restart_phase2():
    http = _stub(
        {
            "POST /projects/proj_1/services/svc_web/restart": (
                200,
                {"id": "svc_web", "ok": True},
            )
        }
    )
    r = RailwayAdapter(_live(2, http)).execute(_req("Railway.restart_service"))
    assert r.status == AdapterStatus.SUCCESS


def test_phase2_locks_deploy():
    r = RailwayAdapter(_live(2, _stub({}))).execute(_req("Railway.deploy"))
    assert r.error == "PHASE_LOCKED"


def test_deploy_phase3():
    http = _stub(
        {
            "POST /projects/proj_1/services/svc_web/deploy": (
                200,
                {"id": "dep_9", "deployment_id": "dep_9"},
            )
        }
    )
    r = RailwayAdapter(_live(3, http)).execute(_req("Railway.deploy"))
    assert r.status == AdapterStatus.SUCCESS
    assert r.external_id == "dep_9"


def test_gated_safe_mode_deny():
    out = execute_railway_gated(
        _req("Railway.deploy"),
        _ctx(safe_mode=True),
        transport=_live(3, _stub({})),
    )
    assert out.gateway.reason == "SAFE_MODE_WRITE_BLOCKED"
    assert out.adapter is None


def test_gated_allow_read():
    audits: list = []
    http = _stub(
        {
            "GET /projects/proj_1/services/svc_web": (
                200,
                {"id": "svc_web", "status": "running"},
            )
        }
    )
    out = execute_railway_gated(
        _req("Railway.service_status", approval=ApprovalState.NOT_REQUIRED),
        _ctx(),
        gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d) or True),
        transport=_live(1, http),
    )
    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.status == AdapterStatus.SUCCESS
    assert audits
