"""Factory + gated path: Gateway → Railway Adapter (mock|live)."""

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
from .adapter import RailwayAdapter
from .flags import (
    railway_api_base,
    railway_live_enabled,
    railway_live_phase,
    railway_token,
)
from .live_transport import LiveRailwayTransport
from .transport import MockRailwayTransport, RailwayTransport


def build_railway_transport(
    *,
    live: bool | None = None,
    phase: int | None = None,
    token: str | None = None,
    http: Any = None,
) -> RailwayTransport:
    use_live = railway_live_enabled() if live is None else bool(live)
    if not use_live:
        return MockRailwayTransport()
    tok = token if token is not None else railway_token()
    if not tok:
        raise ValueError("CORA_RAILWAY_LIVE set but no CORA_RAILWAY_TOKEN/RAILWAY_TOKEN")
    return LiveRailwayTransport(
        token=tok,
        phase=railway_live_phase() if phase is None else phase,
        api_base=railway_api_base(),
        http=http,
    )


@dataclass(frozen=True)
class RailwayGatedResult:
    gateway: GatewayDecision
    adapter: AdapterResult | None

    @property
    def allowed(self) -> bool:
        return self.gateway.decision == GatewayVerdict.ALLOW


def execute_railway_gated(
    request: DispatchRequest,
    context: GatewayContext,
    *,
    gateway: LiveExecutionGateway | None = None,
    transport: RailwayTransport | None = None,
) -> RailwayGatedResult:
    gw = gateway or LiveExecutionGateway()
    decision = gw.evaluate(request, context)
    if decision.decision != GatewayVerdict.ALLOW:
        return RailwayGatedResult(gateway=decision, adapter=None)

    if decision.mode == ExecutionMode.DRY_RUN:
        t: RailwayTransport = MockRailwayTransport()
    elif transport is not None:
        t = transport
    else:
        if not railway_live_enabled():
            blocked = GatewayDecision(
                decision=GatewayVerdict.DENY,
                reason="RAILWAY_LIVE_DISABLED",
                mode=decision.mode,
                approval_state=request.approval_state,
                checks=decision.checks,
                request_id=request.dispatch_id,
                metadata={"adapter_invoked": False, "rollback": True},
            )
            return RailwayGatedResult(gateway=blocked, adapter=None)
        t = build_railway_transport(live=True)

    return RailwayGatedResult(
        gateway=decision, adapter=RailwayAdapter(t).execute(request)
    )
