"""TDD — Discord LIVE (phased · Gateway-gated · stub HTTP)."""

from __future__ import annotations

from typing import Any

from src.jarvis.cora_foundation.adapters import AdapterStatus, DiscordAdapter
from src.jarvis.cora_foundation.adapters.discord.live_transport import LiveDiscordTransport
from src.jarvis.cora_foundation.adapters.discord.path import execute_discord_gated
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchRequest,
)
from src.jarvis.cora_foundation.live_gateway import (
    ExecutionMode,
    GatewayContext,
    GatewayVerdict,
    LiveExecutionGateway,
)


def _req(
    tool: str,
    *,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
) -> DispatchRequest:
    write = any(x in tool for x in ("send", "edit", "delete", "timeout", "kick", "ban"))
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_dc_live",
        tool=tool,
        capability="discord.send" if write else "discord.read",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload if payload is not None else {"channel_id": "ch_1", "content": "hi"},
        metadata={"test": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_dc",
        workspace_id="ws_dc",
        session_valid=True,
        workspace_active=True,
        mode=ExecutionMode.LIVE,
        rate_limit_ok=True,
        audit_available=True,
    )
    base.update(kwargs)
    return GatewayContext(**base)


def _stub_http(responses: dict[str, tuple[int, Any]]):
    def http(method: str, url: str, headers, body):
        auth = str((headers or {}).get("Authorization", ""))
        if "invalid-token" in auth:
            return 401, {"message": "401: Unauthorized"}
        for key, val in responses.items():
            m, path = key.split(" ", 1)
            if method == m and path in url:
                return val
        return 404, {"message": "Unknown Channel"}

    return http


def _live(phase: int, http, token: str = "ok-token") -> LiveDiscordTransport:
    return LiveDiscordTransport(token=token, phase=phase, http=http)


def test_read_channel_live():
    http = _stub_http({"GET /channels/ch_1": (200, {"id": "ch_1", "name": "general"})})
    r = DiscordAdapter(_live(1, http)).execute(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.metadata.get("live") is True


def test_send_message_phase2():
    http = _stub_http(
        {"POST /channels/ch_1/messages": (200, {"id": "m99", "content": "hi"})}
    )
    r = DiscordAdapter(_live(2, http)).execute(
        _req("Discord.send", payload={"channel_id": "ch_1", "content": "hi"})
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "send_message"


def test_phase1_locks_send():
    r = DiscordAdapter(_live(1, _stub_http({}))).execute(
        _req("Discord.send", payload={"channel_id": "ch_1", "content": "x"})
    )
    assert r.error == "PHASE_LOCKED"


def test_moderation_phase3():
    http = _stub_http(
        {"DELETE /guilds/g1/members/u1": (204, {})}
    )
    r = DiscordAdapter(_live(3, http)).execute(
        _req(
            "Discord.kick_user",
            payload={"guild_id": "g1", "user_id": "u1"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS


def test_gated_e_stop_deny():
    out = execute_discord_gated(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        ),
        _ctx(e_stop=True),
        transport=_live(1, _stub_http({})),
    )
    assert out.gateway.reason == "E_STOP"
    assert out.adapter is None


def test_gated_allow_with_audit():
    audits: list = []
    http = _stub_http({"GET /channels/ch_1": (200, {"id": "ch_1"})})
    out = execute_discord_gated(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        ),
        _ctx(),
        gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d) or True),
        transport=_live(1, http),
    )
    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.status == AdapterStatus.SUCCESS
    assert audits


def test_token_invalid():
    r = DiscordAdapter(_live(1, _stub_http({}), token="invalid-token")).execute(
        _req(
            "Discord.read_channel",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"channel_id": "ch_1"},
        )
    )
    assert r.status == AdapterStatus.FAILED
    assert "Unauthorized" in (r.error or "")
