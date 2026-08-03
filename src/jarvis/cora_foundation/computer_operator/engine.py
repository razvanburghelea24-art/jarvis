"""ComputerOperator — observability hand. Never decides. Control denied in 6A."""

from __future__ import annotations

import threading
from typing import Any

from ..audit import AuditEngine, AuditEventType
from ..emergency_stop import EmergencyStopEngine
from ..emergency_stop.states import is_estop_mode
from .allowlist import DEFAULT_ALLOWLIST, AppAllowlist
from .flags import (
    operator_control_enabled_from_env,
    operator_enabled_from_env,
)
from .observer import DesktopObserver, StubDesktopObserver
from .preview import ActionPreview, PreviewStatus, PreviewStep, new_preview_id
from .types import IndicatorState, ObservationSnapshot, OperatorMode

_SCHEMA = "cora.computer_operator.v1"

_CONTROL_METHODS = (
    "click",
    "type_keys",
    "move_mouse",
    "open_app",
    "close_app",
    "write_clipboard",
    "automate",
)


class ComputerOperator:
    """
    Phase 6A: observe desktop.
    Phase 6B: assisted control — only via Planner → Scheduler → Owner → Policy → Dispatcher.

    Golden rule: Operator never decides. Planner is the brain; Operator is the hand.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        control_enabled: bool | None = None,
        allowlist: AppAllowlist | None = None,
        observer: DesktopObserver | None = None,
        audit: AuditEngine | None = None,
        estop: EmergencyStopEngine | None = None,
        clipboard_permitted: bool = False,
    ) -> None:
        self._enabled = operator_enabled_from_env() if enabled is None else bool(enabled)
        self._control_enabled = (
            operator_control_enabled_from_env()
            if control_enabled is None
            else bool(control_enabled)
        )
        self._allowlist = allowlist or AppAllowlist(allowed=set(DEFAULT_ALLOWLIST))
        self._observer = observer or StubDesktopObserver()
        self._audit = audit
        self._estop = estop
        self._clipboard_permitted = bool(clipboard_permitted)
        self._indicator = IndicatorState.OBSERVE
        self._lock = threading.RLock()
        self._previews: dict[str, ActionPreview] = {}
        self._last_snapshot: ObservationSnapshot | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    @property
    def control_enabled(self) -> bool:
        return self._enabled and self._control_enabled

    def set_control_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._control_enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def indicator(self) -> IndicatorState:
        return self._indicator

    def mode(self) -> OperatorMode:
        return OperatorMode.ASSISTED if self.control_enabled else OperatorMode.OBSERVABILITY

    def observe(self) -> ObservationSnapshot | None:
        """Read-only desktop snapshot. None when module OFF."""
        if not self._enabled:
            return None
        # E-Stop may interrupt sequences; observe remains diagnostic unless hard-halted mid-execute
        if self._estop is not None and self._estop.enabled:
            if not self._estop.allows_capability("Computer.observe"):
                self._set_indicator(IndicatorState.OBSERVE)
                self._emit(
                    AuditEventType.OPERATOR_DENIED,
                    status="estop_block",
                    metadata={"capability": "Computer.observe"},
                )
                return None

        with self._lock:
            self._indicator = IndicatorState.OBSERVE
            snap = self._observer.snapshot(
                allowlist=self._allowlist,
                clipboard_permitted=self._clipboard_permitted,
                indicator=self._indicator,
            )
            self._last_snapshot = snap
        self._emit(
            AuditEventType.OPERATOR_OBSERVE,
            status="ok",
            result=snap.to_public_dict(),
        )
        return snap

    def create_preview(self, *, title: str, steps: list[dict[str, Any]]) -> ActionPreview | None:
        """Build Action Preview (trust UX). Never executes in 6A."""
        if not self._enabled:
            return None
        preview_steps = tuple(
            PreviewStep(
                index=i + 1,
                description=str(s.get("description") or ""),
                capability=s.get("capability"),
                target_app=s.get("target_app"),
            )
            for i, s in enumerate(steps)
        )
        # Deny preview targets outside allowlist
        for step in preview_steps:
            if step.target_app and not self._allowlist.is_allowed(step.target_app):
                denied = ActionPreview(
                    preview_id=new_preview_id(),
                    title=title,
                    steps=preview_steps,
                    status=PreviewStatus.DENIED,
                    executable=False,
                )
                self._emit(
                    AuditEventType.OPERATOR_DENIED,
                    status="allowlist_deny",
                    metadata={"preview_id": denied.preview_id, "app": step.target_app},
                )
                return denied

        preview = ActionPreview(
            preview_id=new_preview_id(),
            title=title,
            steps=preview_steps,
            status=PreviewStatus.WAITING_OWNER,
            requires_owner_approval=True,
            executable=False,
        )
        with self._lock:
            self._previews[preview.preview_id] = preview
            self._indicator = IndicatorState.WAITING_OWNER
        self._emit(
            AuditEventType.OPERATOR_PREVIEW,
            status="waiting_owner",
            result=preview.to_public_dict(),
        )
        # Also set PREVIEW briefly represented in result; indicator shows WAITING_OWNER
        return preview

    def approve_preview(self, preview_id: str, *, owner_id: str) -> ActionPreview | None:
        """Owner marks preview approved — still does NOT execute in 6A."""
        if not self._enabled:
            return None
        if not owner_id:
            raise PermissionError("owner_id required")
        with self._lock:
            existing = self._previews.get(preview_id)
            if existing is None:
                return None
            approved = ActionPreview(
                preview_id=existing.preview_id,
                title=existing.title,
                steps=existing.steps,
                status=PreviewStatus.APPROVED,
                requires_owner_approval=True,
                executable=False,
                created_at=existing.created_at,
            )
            self._previews[preview_id] = approved
            self._indicator = IndicatorState.PREVIEW
        self._emit(
            AuditEventType.OPERATOR_APPROVED,
            status="approved_no_execute",
            metadata={"preview_id": preview_id, "owner_id": owner_id, "executed": False},
        )
        return approved

    def cancel_preview(self, preview_id: str, *, owner_id: str | None = None) -> ActionPreview | None:
        if not self._enabled:
            return None
        with self._lock:
            existing = self._previews.get(preview_id)
            if existing is None:
                return None
            cancelled = ActionPreview(
                preview_id=existing.preview_id,
                title=existing.title,
                steps=existing.steps,
                status=PreviewStatus.CANCELLED,
                requires_owner_approval=True,
                executable=False,
                created_at=existing.created_at,
            )
            self._previews[preview_id] = cancelled
            self._indicator = IndicatorState.OBSERVE
        self._emit(
            AuditEventType.OPERATOR_CANCELLED,
            status="cancelled",
            metadata={"preview_id": preview_id, "owner_id": owner_id},
        )
        return cancelled

    # ── Control surface (Phase 6B) — denied in 6A ─────────────────────────

    def click(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("click")

    def type_keys(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("type_keys")

    def move_mouse(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("move_mouse")

    def open_app(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("open_app")

    def close_app(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("close_app")

    def write_clipboard(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("write_clipboard")

    def automate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self._deny_control("automate")

    def execute_preview(self, preview_id: str, **_kwargs: Any) -> dict[str, Any]:
        """6B only — blocked while control OFF / E-Stop."""
        return self._deny_control("execute_preview", metadata={"preview_id": preview_id})

    def interrupt(self, *, reason: str = "estop") -> None:
        """E-Stop / Owner interrupt — drop to OBSERVE, cancel waiting previews."""
        with self._lock:
            self._indicator = IndicatorState.OBSERVE
            for pid, prev in list(self._previews.items()):
                if prev.status in {PreviewStatus.WAITING_OWNER, PreviewStatus.APPROVED, PreviewStatus.DRAFT}:
                    self._previews[pid] = ActionPreview(
                        preview_id=prev.preview_id,
                        title=prev.title,
                        steps=prev.steps,
                        status=PreviewStatus.CANCELLED,
                        requires_owner_approval=True,
                        executable=False,
                        created_at=prev.created_at,
                    )
        self._emit(
            AuditEventType.OPERATOR_CANCELLED,
            status="interrupted",
            metadata={"reason": reason},
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "control_enabled": self.control_enabled,
            "mode": self.mode().value,
            "indicator": self._indicator.value,
            "schema": _SCHEMA,
            "decides": False,
            "bypasses_planner": False,
            "bypasses_scheduler": False,
            "bypasses_policy": False,
            "allowlist": self._allowlist.to_public_dict(),
            "clipboard_permitted": self._clipboard_permitted,
            "control_methods": list(_CONTROL_METHODS),
            "last_snapshot_id": None
            if self._last_snapshot is None
            else self._last_snapshot.snapshot_id,
        }

    def _deny_control(self, action: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        reason = "control_disabled_phase_6a"
        if self._estop is not None and self._estop.enabled:
            if is_estop_mode(self._estop.current_mode()):
                reason = "estop"
            elif self.control_enabled:
                # Even if flag on, Phase 6A code path still requires full pipeline — deny direct call
                reason = "must_use_planner_scheduler_policy_dispatcher"
        elif self.control_enabled:
            reason = "must_use_planner_scheduler_policy_dispatcher"
        self._emit(
            AuditEventType.OPERATOR_DENIED,
            status=reason,
            metadata={"action": action, **(metadata or {})},
        )
        return {
            "accepted": False,
            "action": action,
            "reason": reason,
            "executed": False,
            "controls": False,
        }

    def _set_indicator(self, state: IndicatorState) -> None:
        with self._lock:
            self._indicator = state

    def _emit(
        self,
        event_type: AuditEventType,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._audit is None or not self._audit.enabled:
            return
        self._audit.append(
            event_type=event_type,
            request_id=f"operator_{self._indicator.value.lower()}",
            status=status,
            source="computer_operator",
            capability="Computer.observe"
            if event_type == AuditEventType.OPERATOR_OBSERVE
            else "Computer.control",
            result=result or {},
            metadata={
                "indicator": self._indicator.value,
                "mode": self.mode().value,
                "control_enabled": self.control_enabled,
                **(metadata or {}),
            },
        )


_OP: ComputerOperator | None = None
_OP_LOCK = threading.Lock()


def get_computer_operator(
    *,
    enabled: bool | None = None,
    audit: AuditEngine | None = None,
    estop: EmergencyStopEngine | None = None,
) -> ComputerOperator:
    global _OP
    with _OP_LOCK:
        if _OP is None:
            _OP = ComputerOperator(enabled=enabled, audit=audit, estop=estop)
        else:
            if enabled is not None:
                _OP.set_enabled(bool(enabled))
        return _OP


def reset_computer_operator_for_tests() -> None:
    global _OP
    with _OP_LOCK:
        _OP = None
