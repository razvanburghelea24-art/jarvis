"""Factory + gated execution path: Gateway → GitHub Adapter (mock|live)."""

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
from .adapter import GitHubAdapter
from .flags import (
    github_api_base,
    github_live_enabled,
    github_live_phase,
    github_token,
)
from .live_transport import LiveGitHubTransport
from .transport import GitHubTransport, MockGitHubTransport


def build_github_transport(
    *,
    live: bool | None = None,
    phase: int | None = None,
    token: str | None = None,
    http: Any = None,
) -> GitHubTransport:
    """Mock by default. Live only when explicitly enabled + token present."""
    use_live = github_live_enabled() if live is None else bool(live)
    if not use_live:
        return MockGitHubTransport()
    tok = token if token is not None else github_token()
    if not tok:
        raise ValueError("CORA_GITHUB_LIVE set but no CORA_GITHUB_TOKEN/GITHUB_TOKEN")
    return LiveGitHubTransport(
        token=tok,
        phase=github_live_phase() if phase is None else phase,
        api_base=github_api_base(),
        http=http,
    )


@dataclass(frozen=True)
class GitHubGatedResult:
    gateway: GatewayDecision
    adapter: AdapterResult | None

    @property
    def allowed(self) -> bool:
        return self.gateway.decision == GatewayVerdict.ALLOW

    @property
    def executed(self) -> bool:
        return self.adapter is not None


def execute_github_gated(
    request: DispatchRequest,
    context: GatewayContext,
    *,
    gateway: LiveExecutionGateway | None = None,
    transport: GitHubTransport | None = None,
) -> GitHubGatedResult:
    """
    Official path:
      DispatchRequest → Live Execution Gateway → (ALLOW) → GitHubAdapter

    DryRun → MockTransport. Live → LiveTransport (or injected).
    DENY → adapter never called.
    """
    gw = gateway or LiveExecutionGateway()
    decision = gw.evaluate(request, context)
    if decision.decision != GatewayVerdict.ALLOW:
        return GitHubGatedResult(gateway=decision, adapter=None)

    if decision.mode == ExecutionMode.DRY_RUN:
        t: GitHubTransport = MockGitHubTransport()
    elif transport is not None:
        t = transport
    else:
        if not github_live_enabled():
            # Fail closed: LIVE mode without flag → no adapter call
            blocked = GatewayDecision(
                decision=GatewayVerdict.DENY,
                reason="GITHUB_LIVE_DISABLED",
                mode=decision.mode,
                approval_state=request.approval_state,
                checks=decision.checks,
                request_id=request.dispatch_id,
                metadata={"adapter_invoked": False, "rollback": True},
            )
            return GitHubGatedResult(gateway=blocked, adapter=None)
        t = build_github_transport(live=True)

    result = GitHubAdapter(t).execute(request)
    return GitHubGatedResult(gateway=decision, adapter=result)
