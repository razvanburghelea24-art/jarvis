"""TDD — Framework Adapter (DispatchRequest → AdapterResult · mock · game-world strict)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.adapters import (
    AdapterStatus,
    FrameworkAdapter,
    MockFrameworkTransport,
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
        plan_id="tplan_fw",
        tool=tool,
        capability="framework.execute",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload={"server": "ny-survival-1"} if payload is None else payload,
        metadata={"test": True},
    )


def test_server_status():
    r = FrameworkAdapter().execute(
        _req("Framework.server_status", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.adapter == "framework"
    assert r.operation == "server_status"
    assert r.metadata.get("live") is False


def test_players():
    r = FrameworkAdapter().execute(
        _req("Framework.players", approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "players"


def test_broadcast():
    r = FrameworkAdapter().execute(
        _req(
            "Framework.broadcast",
            payload={"server": "ny-survival-1", "message": "Restart in 5m"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "broadcast"


def test_heal():
    r = FrameworkAdapter().execute(
        _req(
            "Framework.heal",
            payload={"server": "ny-survival-1", "player_id": "steam_abc"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "heal"


def test_kick():
    r = FrameworkAdapter().execute(
        _req(
            "Framework.kick",
            payload={"server": "ny-survival-1", "player_id": "steam_abc"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "kick"


def test_approval_missing_deny():
    r = FrameworkAdapter().execute(
        _req(
            "Framework.broadcast",
            approval=ApprovalState.PENDING,
            payload={"server": "ny-survival-1", "message": "x"},
        )
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "DENY"


def test_missing_player():
    r = FrameworkAdapter().execute(
        _req("Framework.heal", payload={"server": "ny-survival-1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_PLAYER"


def test_missing_server():
    r = FrameworkAdapter().execute(
        _req("Framework.server_status", payload={}, approval=ApprovalState.NOT_REQUIRED)
    )
    assert r.error == "MISSING_SERVER"


def test_invalid_dispatch_request():
    r = FrameworkAdapter().execute(None)  # type: ignore[arg-type]
    assert r.error == "INVALID_DISPATCH_REQUEST"
    r2 = FrameworkAdapter().execute({"tool": "Framework.heal"})  # type: ignore[arg-type]
    assert r2.error == "INVALID_DISPATCH_REQUEST"
    r3 = FrameworkAdapter().execute(
        _req("Discord.send", payload={"server": "s1", "message": "x"})
    )
    assert r3.error == "INVALID_DISPATCH_REQUEST"


def test_unsupported_operation():
    r = FrameworkAdapter().execute(
        _req("Framework.spawn_dragon", payload={"server": "s1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "UNSUPPORTED_OPERATION"


def test_json_immutable():
    r = FrameworkAdapter().execute(
        _req("Framework.health", approval=ApprovalState.NOT_REQUIRED)
    )
    raw = r.to_canonical_dict()
    assert raw["schema_family"] == "cora.adapter.contracts"
    assert raw["adapter"] == "framework"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        r.status = AdapterStatus.FAILED  # type: ignore[misc]


def test_harness_dispatcher_to_framework_adapter():
    req = RequestValidator().validate(
        {
            "request_id": "req-fw-harness",
            "session_id": "sess-fw",
            "workspace_id": "ws",
            "input": "Construiește și rulează framework pipeline",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    fw_reqs = [r for r in batch.requests if r.tool.startswith("Framework.")]
    assert fw_reqs
    base = fw_reqs[0]
    enriched = DispatchRequest(
        dispatch_id=base.dispatch_id,
        plan_id=base.plan_id,
        tool=base.tool,
        capability=base.capability,
        execution_mode=base.execution_mode,
        approval_state=base.approval_state,
        payload={"server": "ny-survival-1"},
        metadata=dict(base.metadata),
        timestamp=base.timestamp,
    )
    result = FrameworkAdapter(MockFrameworkTransport()).execute(enriched)
    assert result.status == AdapterStatus.SUCCESS
    assert result.operation == "server_status"  # Framework.run → safest read
    assert result.metadata.get("live") is False
