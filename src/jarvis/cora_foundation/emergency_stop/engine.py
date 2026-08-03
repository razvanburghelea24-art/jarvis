"""EmergencyStopEngine — single global safety state SSOT."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..audit import AuditEngine, AuditEventType
from .flags import estop_enabled_from_env
from .policy_gate import is_allowed_under_safety
from .states import SafetyMode, TriggerSource, is_estop_mode
from .storage import JsonSafetyStateStore, SafetyStateStore

_SCHEMA = "cora.estop.v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_estop_path() -> Path:
    import os

    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().parent / "cora_safety_state.json"
    return Path.home() / ".config" / "jarvis" / "cora_safety_state.json"


class EmergencyStopEngine:
    """
    Industrial-style safety gate.

    When module flag is OFF: behaves as NORMAL (no enforcement) — foundation default.
    When ON: loads persisted state at start; E-Stop never auto-clears.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        store: SafetyStateStore | None = None,
        path: Path | str | None = None,
        audit: AuditEngine | None = None,
    ) -> None:
        self._enabled = estop_enabled_from_env() if enabled is None else bool(enabled)
        self._store = store or JsonSafetyStateStore(path or default_estop_path())
        self._audit = audit
        self._lock = threading.RLock()
        self._mode = SafetyMode.NORMAL
        self._reason = ""
        self._trigger = TriggerSource.SYSTEM
        self._updated_at = _now()
        self._loaded = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def load(self) -> SafetyMode:
        """Load persisted state. If ESTOP was active, stay in ESTOP (no auto NORMAL)."""
        with self._lock:
            raw = self._store.load()
            mode_raw = str(raw.get("mode") or SafetyMode.NORMAL.value)
            try:
                self._mode = SafetyMode(mode_raw)
            except ValueError:
                self._mode = SafetyMode.NORMAL
            self._reason = str(raw.get("reason") or "")
            try:
                self._trigger = TriggerSource(str(raw.get("trigger") or TriggerSource.SYSTEM.value))
            except ValueError:
                self._trigger = TriggerSource.SYSTEM
            self._updated_at = str(raw.get("updated_at") or _now())
            self._loaded = True
            return self._mode

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _persist(self) -> None:
        self._store.save(
            {
                "schema": _SCHEMA,
                "mode": self._mode.value,
                "reason": self._reason,
                "trigger": self._trigger.value,
                "updated_at": self._updated_at,
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            return {
                "enabled": self._enabled,
                "mode": self._mode.value if self._enabled else SafetyMode.NORMAL.value,
                "enforcing": self._enabled,
                "reason": self._reason if self._enabled else "",
                "trigger": self._trigger.value if self._enabled else TriggerSource.SYSTEM.value,
                "updated_at": self._updated_at,
                "is_estop": bool(self._enabled and is_estop_mode(self._mode)),
                "is_safe_mode": bool(self._enabled and self._mode == SafetyMode.SAFE_MODE),
                "message": self.status_message(),
            }

    def status_message(self) -> str:
        with self._lock:
            self._ensure_loaded()
            if not self._enabled:
                return "Emergency Stop module is OFF (not enforcing)."
            if self._mode == SafetyMode.NORMAL:
                return "Cora is NORMAL — actions may execute per Policy."
            if self._mode == SafetyMode.SAFE_MODE:
                return "Cora is in SAFE_MODE — external actions are blocked."
            if self._mode == SafetyMode.RECOVERY:
                return "Cora is in RECOVERY — awaiting Owner release to NORMAL."
            if is_estop_mode(self._mode):
                return (
                    f"Cora is in Emergency Stop ({self._mode.value}). "
                    "I cannot execute commands until the state is released."
                )
            return f"Cora safety mode: {self._mode.value}"

    def current_mode(self) -> SafetyMode:
        with self._lock:
            self._ensure_loaded()
            if not self._enabled:
                return SafetyMode.NORMAL
            return self._mode

    def allows_capability(self, capability: str) -> bool:
        with self._lock:
            self._ensure_loaded()
            if not self._enabled:
                return True
            return is_allowed_under_safety(capability, self._mode)

    def enter_safe_mode(
        self,
        *,
        reason: str,
        trigger: TriggerSource = TriggerSource.OWNER,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._transition(
            SafetyMode.SAFE_MODE,
            reason=reason,
            trigger=trigger,
            request_id=request_id,
            audit_enter=AuditEventType.SAFE_MODE_ENTERED,
        )

    def exit_safe_mode(
        self,
        *,
        reason: str = "owner exited safe mode",
        trigger: TriggerSource = TriggerSource.OWNER,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Exit SAFE_MODE → NORMAL (not used for E-Stop release)."""
        with self._lock:
            self._ensure_loaded()
            if self._mode != SafetyMode.SAFE_MODE:
                return self.snapshot()
        return self._transition(
            SafetyMode.NORMAL,
            reason=reason,
            trigger=trigger,
            request_id=request_id,
            audit_enter=AuditEventType.SAFE_MODE_EXITED,
        )

    def trigger(
        self,
        *,
        mode: SafetyMode = SafetyMode.ESTOP_MANUAL,
        reason: str,
        trigger: TriggerSource = TriggerSource.OWNER,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Unified trigger interface (owner/policy/sentinel/runtime/watchdog)."""
        if mode == SafetyMode.SAFE_MODE:
            return self.enter_safe_mode(reason=reason, trigger=trigger, request_id=request_id)
        if not is_estop_mode(mode) and mode != SafetyMode.RECOVERY:
            mode = SafetyMode.ESTOP_MANUAL
        return self._transition(
            mode,
            reason=reason,
            trigger=trigger,
            request_id=request_id,
            audit_enter=AuditEventType.ESTOP_TRIGGERED,
        )

    def release(
        self,
        *,
        owner_id: str,
        reason: str = "owner released e-stop",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Only Owner path — moves E-Stop → RECOVERY → NORMAL (audited)."""
        if not owner_id:
            raise PermissionError("owner_id required to release E-Stop")
        rid = request_id or f"cmd_estop_release_{uuid.uuid4().hex}"
        # Step into RECOVERY then NORMAL so audit trail shows recovery.
        self._transition(
            SafetyMode.RECOVERY,
            reason=f"recovery after release by {owner_id}: {reason}",
            trigger=TriggerSource.OWNER,
            request_id=rid,
            audit_enter=AuditEventType.ESTOP_RELEASED,
            extra_meta={"owner_id": owner_id},
        )
        return self._transition(
            SafetyMode.NORMAL,
            reason=f"released by owner {owner_id}: {reason}",
            trigger=TriggerSource.OWNER,
            request_id=rid,
            audit_enter=None,
            extra_meta={"owner_id": owner_id, "phase": "normalized"},
        )

    def _transition(
        self,
        mode: SafetyMode,
        *,
        reason: str,
        trigger: TriggerSource,
        request_id: str | None,
        audit_enter: AuditEventType | None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            if not self._enabled:
                # Module OFF: record intent in snapshot message only — do not persist enforcement.
                return {
                    **self.snapshot(),
                    "accepted": False,
                    "note": "CORA_ESTOP_ENABLED is OFF — transition not enforced",
                }
            prev = self._mode
            self._mode = mode
            self._reason = reason
            self._trigger = trigger
            self._updated_at = _now()
            self._persist()
            snap = {
                "enabled": self._enabled,
                "mode": self._mode.value,
                "previous": prev.value,
                "reason": self._reason,
                "trigger": self._trigger.value,
                "updated_at": self._updated_at,
                "accepted": True,
                "message": self.status_message(),
            }
        if audit_enter is not None and self._audit is not None and self._audit.enabled:
            meta = {"reason": reason, "trigger": trigger.value, "mode": mode.value, "previous": prev.value}
            if extra_meta:
                meta.update(extra_meta)
            self._audit.enqueue(
                event_type=audit_enter,
                request_id=request_id or f"cmd_safety_{uuid.uuid4().hex}",
                status=mode.value,
                metadata=meta,
            )
        return snap


_ENGINE: EmergencyStopEngine | None = None
_LOCK = threading.Lock()


def get_emergency_stop(
    *,
    enabled: bool | None = None,
    path: Path | str | None = None,
    audit: AuditEngine | None = None,
) -> EmergencyStopEngine:
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = EmergencyStopEngine(enabled=enabled, path=path, audit=audit)
            _ENGINE.load()
        elif enabled is not None:
            _ENGINE.set_enabled(bool(enabled))
        return _ENGINE


def reset_emergency_stop_for_tests() -> None:
    global _ENGINE
    with _LOCK:
        _ENGINE = None
