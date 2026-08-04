"""TDD — Discord Adapter (DispatchRequest → AdapterResult · mock transport)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.adapters import (
    AdapterStatus,
    DiscordAdapter,
    MockDiscordTransport,
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
        plan_id="tplan_dc",
        tool=tool,
        capability="discord.send",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload or {"channel_id": "ch_123"},
        metadata={"test": True},
    )


def test_send_message():
    r = DiscordAdapter().execute(
        _req(
            "Discord.send_message",
            payload={"channel_id": "ch_1", "content": "hello Cora"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.adapter == "discord"
    assert r.operation == "send_message"
    assert r.external_id
    assert r.metadata.get("live") is False


def test_edit_message():
    r = DiscordAdapter().execute(
        _req(
            "Discord.edit_message",
            payload={"channel_id": "ch_1", "message_id": "m9", "content": "edited"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "edit_message"


def test_delete_message():
    r = DiscordAdapter().execute(
        _req(
            "Discord.delete_message",
            payload={"channel_id": "ch_1", "message_id": "m9"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "delete_message"


def test_read_channel():
    r = DiscordAdapter().execute(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "read_channel"


def test_read_message():
    r = DiscordAdapter().execute(
        _req(
            "Discord.read_message",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1", "message_id": "m1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "read_message"


def test_approval_missing_deny():
    r = DiscordAdapter().execute(
        _req(
            "Discord.send",
            approval=ApprovalState.PENDING,
            payload={"channel_id": "ch_1", "content": "x"},
        )
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "DENY"


def test_missing_channel():
    r = DiscordAdapter().execute(
        _req("Discord.send_message", payload={"content": "no channel"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_CHANNEL"


def test_invalid_dispatch_request():
    r = DiscordAdapter().execute(None)  # type: ignore[arg-type]
    assert r.error == "INVALID_DISPATCH_REQUEST"
    r2 = DiscordAdapter().execute({"tool": "Discord.send"})  # type: ignore[arg-type]
    assert r2.error == "INVALID_DISPATCH_REQUEST"
    r3 = DiscordAdapter().execute(
        _req("GitHub.create_pr", payload={"channel_id": "ch", "content": "x"})
    )
    assert r3.error == "INVALID_DISPATCH_REQUEST"


def test_unsupported_operation():
    r = DiscordAdapter().execute(
        _req("Discord.nuke_server", payload={"channel_id": "ch_1"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "UNSUPPORTED_OPERATION"


def test_json_immutable():
    r = DiscordAdapter().execute(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        )
    )
    raw = r.to_canonical_dict()
    assert raw["schema_family"] == "cora.adapter.contracts"
    assert raw["adapter"] == "discord"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        r.status = AdapterStatus.FAILED  # type: ignore[misc]


def test_harness_dispatcher_to_discord_adapter():
    req = RequestValidator().validate(
        {
            "request_id": "req-dc-harness",
            "session_id": "sess-dc",
            "workspace_id": "ws",
            "input": "Fă un plan și trimite anunț pe Discord",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    dc_reqs = [r for r in batch.requests if r.tool.startswith("Discord.")]
    assert dc_reqs
    gh_req = dc_reqs[0]
    enriched = DispatchRequest(
        dispatch_id=gh_req.dispatch_id,
        plan_id=gh_req.plan_id,
        tool=gh_req.tool,
        capability=gh_req.capability,
        execution_mode=gh_req.execution_mode,
        approval_state=gh_req.approval_state,
        payload={"channel_id": "ops-announce", "content": "Release ready"},
        metadata=dict(gh_req.metadata),
        timestamp=gh_req.timestamp,
    )
    result = DiscordAdapter(MockDiscordTransport()).execute(enriched)
    assert result.status == AdapterStatus.SUCCESS
    assert result.operation == "send_message"
    assert result.metadata.get("live") is False
