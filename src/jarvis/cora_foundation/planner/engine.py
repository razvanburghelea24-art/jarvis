"""PlannerEngine — create/update/approve/reject/expire plans. Never execute."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from ..audit import AuditEngine, AuditEventType
from ..gateway.capabilities import CapabilityRegistry, default_capability_registry
from .context import PlannerContext
from .flags import planner_enabled_from_env
from .synthesize import plan_from_dict_patch, synthesize_plan
from .types import Plan, PlanStatus

_SCHEMA = "cora.planner.engine.v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PlannerEngine:
    """
    Plan-only brain.

    Forbidden: live integration APIs, file write, memory mutations,
    capability dispatch. Allowed: read context → emit Plan + audit events.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        audit: AuditEngine | None = None,
        capabilities: CapabilityRegistry | None = None,
    ) -> None:
        self._enabled = planner_enabled_from_env() if enabled is None else bool(enabled)
        self._audit = audit
        self._capabilities = capabilities or default_capability_registry()
        self._lock = threading.RLock()
        self._plans: dict[str, Plan] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def get(self, plan_id: str) -> Plan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def list_plans(self) -> list[Plan]:
        with self._lock:
            return list(self._plans.values())

    def create_plan(self, ctx: PlannerContext) -> Plan | None:
        """Observe context → Plan. Returns None when module OFF."""
        if not self._enabled:
            return None
        plan = synthesize_plan(ctx, registry=self._capabilities, status=PlanStatus.READY)
        with self._lock:
            self._plans[plan.plan_id] = plan
        self._audit_plan(AuditEventType.PLAN_CREATED, plan, ctx)
        return plan

    def update_plan(self, plan_id: str, patch: dict[str, Any], *, request_id: str | None = None) -> Plan | None:
        if not self._enabled:
            return None
        with self._lock:
            existing = self._plans.get(plan_id)
            if existing is None:
                return None
            if existing.status in {PlanStatus.REJECTED, PlanStatus.EXPIRED}:
                return None
            updated = plan_from_dict_patch(existing, patch)
            # force non-terminal unless patch sets status carefully
            if updated.status == PlanStatus.APPROVED:
                # approval goes through approve_plan
                updated = plan_from_dict_patch(updated, {"status": PlanStatus.READY.value})
            self._plans[plan_id] = updated
        self._audit_plan(
            AuditEventType.PLAN_UPDATED,
            updated,
            request_id=request_id or updated.request_id,
        )
        return updated

    def approve_plan(self, plan_id: str, *, owner_id: str, request_id: str | None = None) -> Plan | None:
        """Mark plan APPROVED — still does not execute."""
        if not self._enabled:
            return None
        if not owner_id:
            raise PermissionError("owner_id required to approve plan")
        with self._lock:
            existing = self._plans.get(plan_id)
            if existing is None:
                return None
            if existing.status not in {PlanStatus.DRAFT, PlanStatus.READY}:
                return None
            updated = plan_from_dict_patch(existing, {"status": PlanStatus.APPROVED.value})
            self._plans[plan_id] = updated
        self._audit_plan(
            AuditEventType.PLAN_APPROVED,
            updated,
            request_id=request_id or updated.request_id,
            owner_id=owner_id,
        )
        return updated

    def reject_plan(
        self,
        plan_id: str,
        *,
        owner_id: str,
        reason: str = "",
        request_id: str | None = None,
    ) -> Plan | None:
        if not self._enabled:
            return None
        if not owner_id:
            raise PermissionError("owner_id required to reject plan")
        with self._lock:
            existing = self._plans.get(plan_id)
            if existing is None:
                return None
            updated = plan_from_dict_patch(
                existing,
                {
                    "status": PlanStatus.REJECTED.value,
                    "summary": f"{existing.summary} | rejected: {reason}".strip(" |"),
                },
            )
            self._plans[plan_id] = updated
        self._audit_plan(
            AuditEventType.PLAN_REJECTED,
            updated,
            request_id=request_id or updated.request_id,
            owner_id=owner_id,
            metadata={"reason": reason},
        )
        return updated

    def expire_plan(self, plan_id: str, *, request_id: str | None = None) -> Plan | None:
        if not self._enabled:
            return None
        with self._lock:
            existing = self._plans.get(plan_id)
            if existing is None:
                return None
            updated = plan_from_dict_patch(existing, {"status": PlanStatus.EXPIRED.value})
            self._plans[plan_id] = updated
        self._audit_plan(
            AuditEventType.PLAN_EXPIRED,
            updated,
            request_id=request_id or updated.request_id,
        )
        return updated

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "schema": _SCHEMA,
                "plan_only": True,
                "executes": False,
                "writes_memory": False,
                "plan_count": len(self._plans),
            }

    def _audit_plan(
        self,
        event_type: AuditEventType,
        plan: Plan,
        ctx: PlannerContext | None = None,
        *,
        request_id: str | None = None,
        owner_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._audit is None or not self._audit.enabled:
            return
        identity = (ctx.identity if ctx is not None else {}) or {}
        rid = request_id or (ctx.request_id if ctx is not None else None) or plan.request_id or plan.plan_id
        oid = owner_id or identity.get("who")
        if isinstance(identity.get("owner"), dict):
            oid = oid or identity["owner"].get("owner_id")
        self._audit.append(
            event_type=event_type,
            request_id=str(rid),
            status="ok",
            owner_id=str(oid) if oid else None,
            workspace_id=(
                (identity.get("where") or {}).get("workspace_id")
                if isinstance(identity.get("where"), dict)
                else None
            ),
            session_id=identity.get("active_session"),
            source=ctx.source if ctx is not None else "planner",
            capability=",".join(plan.required_capabilities) if plan.required_capabilities else None,
            risk_level=plan.risk_level.value,
            result={
                "plan_id": plan.plan_id,
                "kind": plan.kind.value,
                "status": plan.status.value,
                "requires_owner_approval": plan.requires_owner_approval,
                "executable": False,
            },
            metadata={
                "goal": plan.goal[:200],
                "estimated_cost": plan.estimated_cost,
                "estimated_duration_s": plan.estimated_duration_s,
                "risk_reason": plan.risk_reason,
                **(metadata or {}),
                "recorded_at": _now(),
            },
        )


_ENGINE: PlannerEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_planner_engine(*, enabled: bool | None = None, audit: AuditEngine | None = None) -> PlannerEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = PlannerEngine(enabled=enabled, audit=audit)
        else:
            if enabled is not None:
                _ENGINE.set_enabled(bool(enabled))
        return _ENGINE


def reset_planner_engine_for_tests() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None
