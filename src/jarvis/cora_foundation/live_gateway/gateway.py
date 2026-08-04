"""Live Execution Gateway v1 — DispatchRequest → GatewayDecision (airlock).

Never executes adapters · never mutates DispatchRequest · never talks to integrations.
Law: No live/world side-effect without Gateway ALLOW.
"""

from __future__ import annotations

from typing import Any, Callable

from ..dispatcher.contracts import ApprovalState, DispatchRequest
from .context import WRITE_CAPABILITIES, GatewayContext
from .decision import (
    CheckResult,
    ExecutionMode,
    GatewayDecision,
    GatewayVerdict,
)

# Fixed immutable check order
CHECK_ORDER: tuple[str, ...] = (
    "dispatch_request_valid",
    "session_valid",
    "workspace_active",
    "owner_approval",
    "capability_permitted",
    "e_stop",
    "safe_mode",
    "rate_limit",
    "audit_available",
    "execution_mode",
)


class LiveExecutionGateway:
    """Central safety airlock before Integration Layer."""

    def __init__(
        self,
        *,
        on_audit: Callable[[GatewayDecision], bool] | None = None,
    ) -> None:
        # on_audit returns False if audit could not be created
        self._on_audit = on_audit

    def evaluate(
        self,
        request: DispatchRequest | Any,
        context: GatewayContext | None = None,
    ) -> GatewayDecision:
        ctx = context or GatewayContext()
        checks: list[CheckResult] = []

        # 1. DispatchRequest valid
        invalid = self._invalid_request(request)
        if invalid:
            return self._deny(
                request,
                ctx,
                checks,
                failed="dispatch_request_valid",
                reason=invalid,
                detail=invalid,
            )
        assert isinstance(request, DispatchRequest)
        checks.append(CheckResult("dispatch_request_valid", True, "ok"))

        # 2. Session valid
        if not ctx.session_valid or not str(ctx.session_id or "").strip():
            return self._deny(
                request,
                ctx,
                checks,
                failed="session_valid",
                reason="SESSION_INVALID",
                detail="session missing or invalid",
            )
        checks.append(CheckResult("session_valid", True, ctx.session_id))

        # 3. Workspace active
        if not ctx.workspace_active or not str(ctx.workspace_id or "").strip():
            return self._deny(
                request,
                ctx,
                checks,
                failed="workspace_active",
                reason="WORKSPACE_INACTIVE",
                detail="workspace missing or inactive",
            )
        checks.append(CheckResult("workspace_active", True, ctx.workspace_id))

        # 4. Owner Approval
        if not self._approval_ok(request):
            return self._deny(
                request,
                ctx,
                checks,
                failed="owner_approval",
                reason="APPROVAL_MISSING",
                detail=request.approval_state.value,
            )
        checks.append(
            CheckResult("owner_approval", True, request.approval_state.value)
        )

        # 5. Capability permitted
        if request.capability not in ctx.permitted_capabilities():
            return self._deny(
                request,
                ctx,
                checks,
                failed="capability_permitted",
                reason="CAPABILITY_FORBIDDEN",
                detail=request.capability,
            )
        checks.append(CheckResult("capability_permitted", True, request.capability))

        # 6. E-Stop / Kill Switch
        if ctx.e_stop or ctx.kill_switch:
            return self._deny(
                request,
                ctx,
                checks,
                failed="e_stop",
                reason="E_STOP" if ctx.e_stop else "KILL_SWITCH",
                detail=f"e_stop={ctx.e_stop} kill_switch={ctx.kill_switch}",
            )
        checks.append(CheckResult("e_stop", True, "clear"))

        # 7. Safe Mode + write
        is_write = request.capability in WRITE_CAPABILITIES or self._looks_like_write(
            request
        )
        if ctx.safe_mode and is_write:
            return self._deny(
                request,
                ctx,
                checks,
                failed="safe_mode",
                reason="SAFE_MODE_WRITE_BLOCKED",
                detail=request.capability,
            )
        checks.append(
            CheckResult(
                "safe_mode",
                True,
                "ok" if not ctx.safe_mode else "safe_mode_read_ok",
            )
        )

        # 8. Rate limit
        if not ctx.rate_limit_ok:
            return self._deny(
                request,
                ctx,
                checks,
                failed="rate_limit",
                reason="RATE_LIMIT",
                detail="rate limit exceeded",
            )
        checks.append(CheckResult("rate_limit", True, "ok"))

        # 9. Audit available (+ create trail)
        if not ctx.audit_available:
            return self._deny(
                request,
                ctx,
                checks,
                failed="audit_available",
                reason="AUDIT_UNAVAILABLE",
                detail="audit system unavailable",
            )
        # provisional decision for audit payload
        provisional = GatewayDecision(
            decision=GatewayVerdict.ALLOW,
            reason="PENDING_AUDIT",
            mode=ctx.mode,
            approval_state=request.approval_state,
            checks=tuple(checks),
            request_id=request.dispatch_id,
            metadata={"phase": "pre_audit"},
        )
        if self._on_audit is not None:
            if not self._on_audit(provisional):
                return self._deny(
                    request,
                    ctx,
                    checks,
                    failed="audit_available",
                    reason="AUDIT_UNAVAILABLE",
                    detail="audit record failed",
                )
        elif not ctx.audit_record_ok:
            return self._deny(
                request,
                ctx,
                checks,
                failed="audit_available",
                reason="AUDIT_UNAVAILABLE",
                detail="audit record failed",
            )
        checks.append(CheckResult("audit_available", True, "recorded"))

        # 10. Execution Mode — always recorded; both DryRun and Live can ALLOW
        if ctx.mode not in {ExecutionMode.DRY_RUN, ExecutionMode.LIVE}:
            return self._deny(
                request,
                ctx,
                checks,
                failed="execution_mode",
                reason="INVALID_MODE",
                detail=str(ctx.mode),
            )
        checks.append(CheckResult("execution_mode", True, ctx.mode.value))

        decision = GatewayDecision(
            decision=GatewayVerdict.ALLOW,
            reason="ALL_CHECKS_PASSED",
            mode=ctx.mode,
            approval_state=request.approval_state,
            checks=tuple(checks),
            request_id=request.dispatch_id,
            metadata={
                "adapter_invoked": False,
                "dispatch_id": request.dispatch_id,
                "plan_id": request.plan_id,
                "tool": request.tool,
                "capability": request.capability,
                "session_id": ctx.session_id,
                "workspace_id": ctx.workspace_id,
                "side_effects": False if ctx.mode == ExecutionMode.DRY_RUN else None,
            },
        )
        return decision

    def _deny(
        self,
        request: Any,
        ctx: GatewayContext,
        checks: list[CheckResult],
        *,
        failed: str,
        reason: str,
        detail: str,
    ) -> GatewayDecision:
        checks.append(CheckResult(failed, False, detail))
        # mark remaining checks as not run
        started = {c.name for c in checks}
        for name in CHECK_ORDER:
            if name not in started:
                checks.append(CheckResult(name, False, "skipped"))
                break  # only note first skipped after fail; keep short
        approval = (
            request.approval_state
            if isinstance(request, DispatchRequest)
            else ApprovalState.PENDING
        )
        req_id = getattr(request, "dispatch_id", "") or ""
        decision = GatewayDecision(
            decision=GatewayVerdict.DENY,
            reason=reason,
            mode=ctx.mode,
            approval_state=approval,
            checks=tuple(checks),
            request_id=req_id,
            metadata={
                "adapter_invoked": False,
                "failed_check": failed,
                "detail": detail,
            },
        )
        if self._on_audit is not None and ctx.audit_available:
            try:
                self._on_audit(decision)
            except Exception:  # noqa: BLE001 — deny path must not raise
                pass
        return decision

    @staticmethod
    def _invalid_request(request: Any) -> str | None:
        if request is None or not isinstance(request, DispatchRequest):
            return "INVALID_DISPATCH_REQUEST"
        if not request.dispatch_id or not request.plan_id or not request.tool:
            return "INVALID_DISPATCH_REQUEST"
        if not request.capability:
            return "INVALID_DISPATCH_REQUEST"
        return None

    @staticmethod
    def _approval_ok(request: DispatchRequest) -> bool:
        state = request.approval_state
        if state in {ApprovalState.DENIED, ApprovalState.PENDING}:
            return False
        is_write = (
            request.capability in WRITE_CAPABILITIES
            or LiveExecutionGateway._looks_like_write(request)
        )
        if is_write:
            return state == ApprovalState.GRANTED
        return state in {ApprovalState.GRANTED, ApprovalState.NOT_REQUIRED}

    @staticmethod
    def _looks_like_write(request: DispatchRequest) -> bool:
        tool = request.tool.lower()
        write_tokens = (
            "create",
            "send",
            "deploy",
            "delete",
            "edit",
            "write",
            "execute",
            "restart",
            "rollback",
            "ban",
            "kick",
            "heal",
            "broadcast",
        )
        return any(t in tool for t in write_tokens)
