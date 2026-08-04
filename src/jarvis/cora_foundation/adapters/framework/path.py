"""Factory + gated path: Gateway → Framework Adapter (mock|live)."""

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
from .adapter import FrameworkAdapter
from .flags import (
    framework_api_base,
    framework_live_enabled,
    framework_live_phase,
    framework_token,
)
from .live_transport import LiveFrameworkTransport
from .transport import FrameworkTransport, MockFrameworkTransport


def build_framework_transport(
    *,
    live: bool | None = None,
    phase: int | None = None,
    token: str | None = None,
    http: Any = None,
) -> FrameworkTransport:
    use_live = framework_live_enabled() if live is None else bool(live)
    if not use_live:
        return MockFrameworkTransport()
    tok = token if token is not None else framework_token()
    if not tok:
        raise ValueError("CORA_FRAMEWORK_LIVE set but no CORA_FRAMEWORK_TOKEN")
    return LiveFrameworkTransport(
        token=tok,
        phase=framework_live_phase() if phase is None else phase,
        api_base=framework_api_base(),
        http=http,
    )


@dataclass(frozen=True)
class FrameworkGatedResult:
    gateway: GatewayDecision
    adapter: AdapterResult | None

    @property
    def allowed(self) -> bool:
        return self.gateway.decision == GatewayVerdict.ALLOW


def execute_framework_gated(
    request: DispatchRequest,
    context: GatewayContext,
    *,
    gateway: LiveExecutionGateway | None = None,
    transport: FrameworkTransport | None = None,
) -> FrameworkGatedResult:
    gw = gateway or LiveExecutionGateway()
    decision = gw.evaluate(request, context)
    if decision.decision != GatewayVerdict.ALLOW:
        return FrameworkGatedResult(gateway=decision, adapter=None)

    if decision.mode == ExecutionMode.DRY_RUN:
        t: FrameworkTransport = MockFrameworkTransport()
    elif transport is not None:
        t = transport
    else:
        if not framework_live_enabled():
            blocked = GatewayDecision(
                decision=GatewayVerdict.DENY,
                reason="FRAMEWORK_LIVE_DISABLED",
                mode=decision.mode,
                approval_state=request.approval_state,
                checks=decision.checks,
                request_id=request.dispatch_id,
                metadata={"adapter_invoked": False, "rollback": True},
            )
            return FrameworkGatedResult(gateway=blocked, adapter=None)
        t = build_framework_transport(live=True)

    return FrameworkGatedResult(
        gateway=decision, adapter=FrameworkAdapter(t).execute(request)
    )
