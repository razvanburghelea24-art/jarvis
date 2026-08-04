"""Factory + gated path: Gateway → n8n Adapter (mock|live)."""

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
from .adapter import N8NAdapter
from .flags import n8n_api_base, n8n_live_enabled, n8n_live_phase, n8n_token
from .live_transport import LiveN8NTransport
from .transport import MockN8NTransport, N8NTransport


def build_n8n_transport(
    *,
    live: bool | None = None,
    phase: int | None = None,
    token: str | None = None,
    http: Any = None,
) -> N8NTransport:
    use_live = n8n_live_enabled() if live is None else bool(live)
    if not use_live:
        return MockN8NTransport()
    tok = token if token is not None else n8n_token()
    if not tok:
        raise ValueError("CORA_N8N_LIVE set but no CORA_N8N_TOKEN/N8N_API_KEY")
    return LiveN8NTransport(
        token=tok,
        phase=n8n_live_phase() if phase is None else phase,
        api_base=n8n_api_base(),
        http=http,
    )


@dataclass(frozen=True)
class N8NGatedResult:
    gateway: GatewayDecision
    adapter: AdapterResult | None

    @property
    def allowed(self) -> bool:
        return self.gateway.decision == GatewayVerdict.ALLOW


def execute_n8n_gated(
    request: DispatchRequest,
    context: GatewayContext,
    *,
    gateway: LiveExecutionGateway | None = None,
    transport: N8NTransport | None = None,
) -> N8NGatedResult:
    gw = gateway or LiveExecutionGateway()
    decision = gw.evaluate(request, context)
    if decision.decision != GatewayVerdict.ALLOW:
        return N8NGatedResult(gateway=decision, adapter=None)

    if decision.mode == ExecutionMode.DRY_RUN:
        t: N8NTransport = MockN8NTransport()
    elif transport is not None:
        t = transport
    else:
        if not n8n_live_enabled():
            blocked = GatewayDecision(
                decision=GatewayVerdict.DENY,
                reason="N8N_LIVE_DISABLED",
                mode=decision.mode,
                approval_state=request.approval_state,
                checks=decision.checks,
                request_id=request.dispatch_id,
                metadata={"adapter_invoked": False, "rollback": True},
            )
            return N8NGatedResult(gateway=blocked, adapter=None)
        t = build_n8n_transport(live=True)

    return N8NGatedResult(
        gateway=decision, adapter=N8NAdapter(t).execute(request)
    )
