"""TDD — Framework LIVE (phased · Gateway-gated · stub HTTP · READ before WRITE)."""

from __future__ import annotations

from typing import Any

from src.jarvis.cora_foundation.adapters import AdapterStatus, FrameworkAdapter
from src.jarvis.cora_foundation.adapters.framework.live_transport import LiveFrameworkTransport
from src.jarvis.cora_foundation.adapters.framework.path import execute_framework_gated
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
    write = any(
        x in tool
        for x in (
            "broadcast",
            "heal",
            "kick",
            "ban",
            "grow",
            "teleport",
            "time_set",
            "weather_set",
            "points",
            "economy",
        )
    )
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_fw_live",
        tool=tool,
        capability=capability or ("framework.execute" if write else "framework.read"),
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload if payload is not None else {"server": "ny-1"},
        metadata={"test": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_fw",
        workspace_id="ws_fw",
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


def _live(phase: int, http, token: str = "ok-token") -> LiveFrameworkTransport:
    return LiveFrameworkTransport(token=token, phase=phase, http=http)


def test_server_status_read_phase1():
    http = _stub(
        {"GET /servers/ny-1/server_status": (200, {"online": True, "players": 3})}
    )
    r = FrameworkAdapter(_live(1, http)).execute(
        _req("Framework.server_status", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.metadata.get("live") is True


def test_phase1_locks_broadcast():
    r = FrameworkAdapter(_live(1, _stub({}))).execute(
        _req("Framework.broadcast", payload={"server": "ny-1", "message": "x"})
    )
    assert r.error == "PHASE_LOCKED"


def test_broadcast_phase2():
    http = _stub({"POST /servers/ny-1/broadcast": (200, {"id": "b1", "ok": True})})
    r = FrameworkAdapter(_live(2, http)).execute(
        _req("Framework.broadcast", payload={"server": "ny-1", "message": "restart"})
    )
    assert r.status == AdapterStatus.SUCCESS


def test_kick_phase3():
    http = _stub({"POST /servers/ny-1/kick": (200, {"id": "steam_1", "ok": True})})
    r = FrameworkAdapter(_live(3, http)).execute(
        _req("Framework.kick", payload={"server": "ny-1", "player_id": "steam_1"})
    )
    assert r.status == AdapterStatus.SUCCESS


def test_phase2_locks_kick():
    r = FrameworkAdapter(_live(2, _stub({}))).execute(
        _req("Framework.kick", payload={"server": "ny-1", "player_id": "p1"})
    )
    assert r.error == "PHASE_LOCKED"


def test_gated_safe_mode_deny():
    out = execute_framework_gated(
        _req("Framework.broadcast", payload={"server": "ny-1", "message": "x"}),
        _ctx(safe_mode=True),
        transport=_live(2, _stub({})),
    )
    assert out.gateway.reason == "SAFE_MODE_WRITE_BLOCKED"
    assert out.adapter is None


def test_gated_allow_read():
    audits: list = []
    http = _stub({"GET /servers/ny-1/health": (200, {"ok": True})})
    out = execute_framework_gated(
        _req("Framework.health", approval=ApprovalState.NOT_REQUIRED),
        _ctx(),
        gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d) or True),
        transport=_live(1, http),
    )
    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.status == AdapterStatus.SUCCESS
    assert audits
