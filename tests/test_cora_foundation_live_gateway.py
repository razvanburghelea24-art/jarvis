"""TDD — Live Execution Gateway (DispatchRequest → GatewayDecision · never execute)."""

from __future__ import annotations

import json

import pytest

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
from src.jarvis.cora_foundation.live_gateway import (
    ExecutionMode,
    GatewayContext,
    GatewayVerdict,
    LiveExecutionGateway,
)
from src.jarvis.cora_foundation.planner import PlannerRouter
from src.jarvis.cora_foundation.tool_routing import ToolRouter


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _req(
    *,
    tool: str = "GitHub.create_pr",
    capability: str = "github.write",
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
) -> DispatchRequest:
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_gw",
        tool=tool,
        capability=capability,
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload if payload is not None else {"repo": "o/r", "title": "x"},
        metadata={"test": True},
    )


def _ok_ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_1",
        workspace_id="ws_1",
        session_valid=True,
        workspace_active=True,
        e_stop=False,
        kill_switch=False,
        safe_mode=False,
        rate_limit_ok=True,
        audit_available=True,
        audit_record_ok=True,
        mode=ExecutionMode.DRY_RUN,
    )
    base.update(kwargs)
    return GatewayContext(**base)


def test_approval_missing_deny():
    d = LiveExecutionGateway().evaluate(
        _req(approval=ApprovalState.PENDING), _ok_ctx()
    )
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "APPROVAL_MISSING"
    assert d.metadata.get("adapter_invoked") is False


def test_e_stop_deny():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(e_stop=True))
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "E_STOP"


def test_safe_mode_write_deny():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(safe_mode=True))
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "SAFE_MODE_WRITE_BLOCKED"


def test_workspace_missing_deny():
    d = LiveExecutionGateway().evaluate(
        _req(), _ok_ctx(workspace_active=False, workspace_id="")
    )
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "WORKSPACE_INACTIVE"


def test_session_invalid_deny():
    d = LiveExecutionGateway().evaluate(
        _req(), _ok_ctx(session_valid=False, session_id="")
    )
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "SESSION_INVALID"


def test_capability_forbidden_deny():
    d = LiveExecutionGateway().evaluate(
        _req(),
        _ok_ctx(allowed_capabilities=frozenset({"discord.send"})),
    )
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "CAPABILITY_FORBIDDEN"


def test_rate_limit_deny():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(rate_limit_ok=False))
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "RATE_LIMIT"


def test_audit_unavailable_deny():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(audit_available=False))
    assert d.decision == GatewayVerdict.DENY
    assert d.reason == "AUDIT_UNAVAILABLE"

    d2 = LiveExecutionGateway(on_audit=lambda _d: False).evaluate(_req(), _ok_ctx())
    assert d2.decision == GatewayVerdict.DENY
    assert d2.reason == "AUDIT_UNAVAILABLE"


def test_dry_run_allow_no_side_effects():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(mode=ExecutionMode.DRY_RUN))
    assert d.decision == GatewayVerdict.ALLOW
    assert d.mode == ExecutionMode.DRY_RUN
    assert d.reason == "ALL_CHECKS_PASSED"
    assert d.metadata.get("side_effects") is False
    assert d.metadata.get("adapter_invoked") is False


def test_live_allow_all_checks():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx(mode=ExecutionMode.LIVE))
    assert d.decision == GatewayVerdict.ALLOW
    assert d.mode == ExecutionMode.LIVE
    assert d.reason == "ALL_CHECKS_PASSED"
    # Gateway still does not invoke adapters
    assert d.metadata.get("adapter_invoked") is False


def test_does_not_mutate_dispatch_request():
    req = _req()
    before = req.to_canonical_dict()
    LiveExecutionGateway().evaluate(req, _ok_ctx())
    assert req.to_canonical_dict() == before


def test_json_immutable():
    d = LiveExecutionGateway().evaluate(_req(), _ok_ctx())
    raw = d.to_canonical_dict()
    assert raw["schema_family"] == "cora.live.gateway.contracts"
    assert raw["kind"] == "GatewayDecision"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        d.decision = GatewayVerdict.DENY  # type: ignore[misc]


def test_harness_dispatcher_to_gateway():
    req = RequestValidator().validate(
        {
            "request_id": "req-leg-harness",
            "session_id": "sess-leg",
            "workspace_id": "ws",
            "input": "Creează un PR pe GitHub",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    assert batch.requests

    dispatch_req = batch.requests[0]
    before = dispatch_req.to_canonical_dict()
    gw_ctx = _ok_ctx(
        session_id=req.session_id,
        workspace_id=req.workspace_id,
        mode=ExecutionMode.DRY_RUN,
    )
    decision = LiveExecutionGateway().evaluate(dispatch_req, gw_ctx)
    assert decision.decision == GatewayVerdict.ALLOW
    assert decision.mode == ExecutionMode.DRY_RUN
    assert decision.metadata.get("adapter_invoked") is False
    assert dispatch_req.to_canonical_dict() == before

    blocked = LiveExecutionGateway().evaluate(
        dispatch_req, _ok_ctx(session_id=req.session_id, workspace_id=req.workspace_id, e_stop=True)
    )
    assert blocked.decision == GatewayVerdict.DENY
    assert blocked.reason == "E_STOP"


def test_framework_health_not_confused_with_heal_write():
    """Regression: substring 'heal' inside 'health' must not force GRANTED."""
    d = LiveExecutionGateway().evaluate(
        _req(
            tool="Framework.health",
            capability="framework.read",
            approval=ApprovalState.NOT_REQUIRED,
        ),
        _ok_ctx(mode=ExecutionMode.LIVE),
    )
    assert d.decision == GatewayVerdict.ALLOW

    write = LiveExecutionGateway().evaluate(
        _req(
            tool="Framework.heal",
            capability="framework.execute",
            approval=ApprovalState.NOT_REQUIRED,
        ),
        _ok_ctx(mode=ExecutionMode.LIVE),
    )
    assert write.decision == GatewayVerdict.DENY
    assert write.reason == "APPROVAL_MISSING"
