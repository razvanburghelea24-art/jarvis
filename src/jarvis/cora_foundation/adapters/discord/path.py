"""Factory + gated path: Gateway → Discord Adapter (mock|live)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...dispatcher.contracts import DispatchRequest
from ...live_gateway import (
    ExecutionMode,
    GatewayContext,
    GatewayDecision,
    GatewayVerdict,
    LiveExecutionGateway,
)
from ..result import AdapterResult
from .adapter import DiscordAdapter
from .flags import discord_api_base, discord_live_enabled, discord_live_phase, discord_token
from .live_transport import LiveDiscordTransport
from .transport import DiscordTransport, MockDiscordTransport


def build_discord_transport(
    *,
    live: bool | None = None,
    phase: int | None = None,
    token: str | None = None,
    http: Any = None,
) -> DiscordTransport:
    use_live = discord_live_enabled() if live is None else bool(live)
    if not use_live:
        return MockDiscordTransport()
    tok = token if token is not None else discord_token()
    if not tok:
        raise ValueError("CORA_DISCORD_LIVE set but no CORA_DISCORD_TOKEN/DISCORD_BOT_TOKEN")
    return LiveDiscordTransport(
        token=tok,
        phase=discord_live_phase() if phase is None else phase,
        api_base=discord_api_base(),
        http=http,
    )


@dataclass(frozen=True)
class DiscordGatedResult:
    gateway: GatewayDecision
    adapter: AdapterResult | None

    @property
    def allowed(self) -> bool:
        return self.gateway.decision == GatewayVerdict.ALLOW


def execute_discord_gated(
    request: DispatchRequest,
    context: GatewayContext,
    *,
    gateway: LiveExecutionGateway | None = None,
    transport: DiscordTransport | None = None,
) -> DiscordGatedResult:
    gw = gateway or LiveExecutionGateway()
    decision = gw.evaluate(request, context)
    if decision.decision != GatewayVerdict.ALLOW:
        return DiscordGatedResult(gateway=decision, adapter=None)

    if decision.mode == ExecutionMode.DRY_RUN:
        t: DiscordTransport = MockDiscordTransport()
    elif transport is not None:
        t = transport
    else:
        if not discord_live_enabled():
            blocked = GatewayDecision(
                decision=GatewayVerdict.DENY,
                reason="DISCORD_LIVE_DISABLED",
                mode=decision.mode,
                approval_state=request.approval_state,
                checks=decision.checks,
                request_id=request.dispatch_id,
                metadata={"adapter_invoked": False, "rollback": True},
            )
            return DiscordGatedResult(gateway=blocked, adapter=None)
        t = build_discord_transport(live=True)

    return DiscordGatedResult(gateway=decision, adapter=DiscordAdapter(t).execute(request))
