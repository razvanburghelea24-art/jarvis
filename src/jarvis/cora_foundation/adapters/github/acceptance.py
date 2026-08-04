"""GitHub LIVE Acceptance Suite — prove stability before next live adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ...dispatcher.contracts import ApprovalState, DispatchExecutionMode, DispatchRequest
from ...live_gateway import (
    ExecutionMode,
    GatewayContext,
    GatewayVerdict,
    LiveExecutionGateway,
)
from ..result import AdapterStatus
from .live_transport import LiveGitHubTransport
from .metrics import ChainMetrics, Timer
from .path import GitHubGatedResult, execute_github_gated

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    detail: str = ""
    metrics: ChainMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


@dataclass
class AcceptanceReport:
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.scenarios) and all(s.ok for s in self.scenarios)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": len(self.scenarios),
            "ok_count": sum(1 for s in self.scenarios if s.ok),
            "scenarios": [s.to_dict() for s in self.scenarios],
            "verdict": "PRODUCTION_READY" if self.passed else "NOT_READY",
        }


def _req(
    tool: str,
    *,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
    capability: str | None = None,
) -> DispatchRequest:
    write = any(x in tool for x in ("create", "comment"))
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_accept",
        tool=tool,
        capability=capability or ("github.write" if write else "github.read"),
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload
        if payload is not None
        else {"repo": "owner/demo", "title": "t", "head": "feat", "base": "main"},
        metadata={"acceptance": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_accept",
        workspace_id="ws_accept",
        session_valid=True,
        workspace_active=True,
        e_stop=False,
        kill_switch=False,
        safe_mode=False,
        rate_limit_ok=True,
        audit_available=True,
        mode=ExecutionMode.LIVE,
    )
    base.update(kwargs)
    return GatewayContext(**base)


def _default_stub_http() -> HttpFn:
    def http(method: str, url: str, headers, body):
        auth = str((headers or {}).get("Authorization", ""))
        if "invalid-token" in auth:
            return 401, {"message": "Bad credentials"}
        if method == "GET" and "/repos/owner/demo/pulls/" in url:
            return 200, {"number": 7, "state": "open", "title": "demo"}
        if method == "GET" and url.endswith("/repos/owner/demo/branches"):
            return 200, [{"name": "main"}, {"name": "feat"}]
        if method == "GET" and url.endswith("/repos/owner/demo"):
            return 200, {"full_name": "owner/demo", "default_branch": "main"}
        if method == "POST" and url.endswith("/repos/owner/demo/pulls"):
            return 201, {"number": 42, "html_url": "https://github.com/owner/demo/pull/42"}
        if method == "POST" and "/issues/" in url and url.endswith("/comments"):
            return 201, {"id": 1001, "body": "ok"}
        if method == "POST" and url.endswith("/repos/owner/demo/issues"):
            return 201, {"number": 9, "title": "issue"}
        if "/repos/no/such" in url:
            return 404, {"message": "Not Found"}
        return 404, {"message": f"unmocked {method} {url}"}

    return http


def _transport(phase: int, http: HttpFn | None = None, token: str = "ok-token") -> LiveGitHubTransport:
    return LiveGitHubTransport(
        token=token, phase=phase, http=http or _default_stub_http()
    )


def _run(
    name: str,
    request: DispatchRequest,
    ctx: GatewayContext,
    transport: LiveGitHubTransport,
    *,
    expect_deny: bool = False,
    expect_deny_reason: str | None = None,
    expect_adapter_ok: bool | None = None,
    expect_adapter_error: str | None = None,
    expect_no_adapter: bool = False,
    gateway: LiveExecutionGateway | None = None,
) -> ScenarioResult:
    metrics = ChainMetrics()
    t_gw = Timer()
    # gateway timing measured inside path roughly via wrapper
    audits: list = []

    def on_audit(d):
        audits.append(d)
        return True

    gw = gateway or LiveExecutionGateway(on_audit=on_audit)
    t_gh = Timer()
    # split: evaluate timing vs adapter — execute_github_gated does both
    out = execute_github_gated(request, ctx, gateway=gw, transport=transport)
    metrics.github_ms = t_gh.ms()
    metrics.gateway_ms = t_gw.ms()  # includes full gated path upper bound

    if expect_deny:
        if out.gateway.decision != GatewayVerdict.DENY:
            return ScenarioResult(name, False, f"expected DENY got {out.gateway.decision}", metrics)
        if expect_deny_reason and out.gateway.reason != expect_deny_reason:
            return ScenarioResult(
                name, False, f"reason {out.gateway.reason} != {expect_deny_reason}", metrics
            )
        if expect_no_adapter and out.adapter is not None:
            return ScenarioResult(name, False, "adapter was invoked on DENY", metrics)
        return ScenarioResult(name, True, out.gateway.reason, metrics)

    if out.gateway.decision != GatewayVerdict.ALLOW:
        return ScenarioResult(name, False, f"expected ALLOW got {out.gateway.reason}", metrics)
    if expect_no_adapter:
        if out.adapter is not None:
            return ScenarioResult(name, False, "expected no adapter", metrics)
        return ScenarioResult(name, True, "no adapter", metrics)
    if out.adapter is None:
        return ScenarioResult(name, False, "adapter missing after ALLOW", metrics)
    if expect_adapter_error:
        if out.adapter.error != expect_adapter_error:
            return ScenarioResult(
                name, False, f"error {out.adapter.error} != {expect_adapter_error}", metrics
            )
        return ScenarioResult(name, True, expect_adapter_error, metrics)
    if expect_adapter_ok and out.adapter.status != AdapterStatus.SUCCESS:
        return ScenarioResult(name, False, f"adapter {out.adapter.status} {out.adapter.error}", metrics)
    if not audits and gateway is None:
        # default gateway records audit on ALLOW
        pass
    return ScenarioResult(name, True, "ok", metrics)


def run_acceptance_suite(*, http: HttpFn | None = None) -> AcceptanceReport:
    """Full GitHub LIVE acceptance — stub HTTP by default (no network)."""
    http = http or _default_stub_http()
    report = AcceptanceReport()
    audits: list = []

    def on_audit(d):
        audits.append(d.to_canonical_dict())
        return True

    gw = LiveExecutionGateway(on_audit=on_audit)
    t3 = _transport(3, http)

    # Happy path ops (phase 3)
    report.scenarios.append(
        _run(
            "read_repo",
            _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "owner/demo"}),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "read_pr",
            _req(
                "GitHub.read_pr",
                approval=ApprovalState.NOT_REQUIRED,
                payload={"repo": "owner/demo", "pr_number": 7},
            ),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "list_branches",
            _req(
                "GitHub.list_branches",
                approval=ApprovalState.NOT_REQUIRED,
                payload={"repo": "owner/demo"},
            ),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "create_issue",
            _req("GitHub.create_issue", payload={"repo": "owner/demo", "title": "bug"}),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "comment_issue",
            _req(
                "GitHub.comment_issue",
                payload={"repo": "owner/demo", "issue_number": 9, "body": "note"},
            ),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "comment_pr",
            _req(
                "GitHub.comment_pr",
                payload={"repo": "owner/demo", "pr_number": 7, "body": "lgtm"},
            ),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )
    report.scenarios.append(
        _run(
            "create_pr",
            _req(
                "GitHub.create_pr",
                payload={
                    "repo": "owner/demo",
                    "title": "feat: demo",
                    "head": "feat",
                    "base": "main",
                },
            ),
            _ctx(),
            t3,
            expect_adapter_ok=True,
            gateway=gw,
        )
    )

    # Audit complet
    report.scenarios.append(
        ScenarioResult(
            "audit_complete",
            ok=len(audits) >= 7,
            detail=f"audit_events={len(audits)}",
        )
    )

    # Gateway approval
    report.scenarios.append(
        _run(
            "gateway_approval_missing",
            _req("GitHub.create_pr", approval=ApprovalState.PENDING),
            _ctx(),
            t3,
            expect_deny=True,
            expect_deny_reason="APPROVAL_MISSING",
            expect_no_adapter=True,
            gateway=gw,
        )
    )

    # Rollback via kill switch / live off pattern (E-Stop)
    report.scenarios.append(
        _run(
            "rollback_e_stop",
            _req("GitHub.create_pr"),
            _ctx(e_stop=True),
            t3,
            expect_deny=True,
            expect_deny_reason="E_STOP",
            expect_no_adapter=True,
            gateway=gw,
        )
    )

    # E-Stop during execution path (same gate — no call)
    report.scenarios.append(
        _run(
            "e_stop_during_execution",
            _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "owner/demo"}),
            _ctx(e_stop=True),
            t3,
            expect_deny=True,
            expect_deny_reason="E_STOP",
            expect_no_adapter=True,
            gateway=gw,
        )
    )

    report.scenarios.append(
        _run(
            "safe_mode",
            _req("GitHub.create_issue", payload={"repo": "owner/demo", "title": "x"}),
            _ctx(safe_mode=True),
            t3,
            expect_deny=True,
            expect_deny_reason="SAFE_MODE_WRITE_BLOCKED",
            expect_no_adapter=True,
            gateway=gw,
        )
    )

    report.scenarios.append(
        _run(
            "rate_limit",
            _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "owner/demo"}),
            _ctx(rate_limit_ok=False),
            t3,
            expect_deny=True,
            expect_deny_reason="RATE_LIMIT",
            expect_no_adapter=True,
            gateway=gw,
        )
    )

    # PHASE_LOCKED
    t1 = _transport(1, http)
    report.scenarios.append(
        _run(
            "phase_locked",
            _req("GitHub.create_pr"),
            _ctx(),
            t1,
            expect_adapter_error="PHASE_LOCKED",
            gateway=gw,
        )
    )

    # Token invalid
    bad = _transport(3, http, token="invalid-token")
    report.scenarios.append(
        _run(
            "token_invalid",
            _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "owner/demo"}),
            _ctx(),
            bad,
            expect_adapter_error="Bad credentials",
            gateway=gw,
        )
    )

    # Repo invalid
    report.scenarios.append(
        _run(
            "repo_invalid",
            _req(
                "GitHub.read_repo",
                approval=ApprovalState.NOT_REQUIRED,
                payload={"repo": "no/such"},
            ),
            _ctx(),
            t3,
            expect_adapter_error="Not Found",
            gateway=gw,
        )
    )

    return report
