"""AuditEngine — append API + optional queue seam (non-blocking evolution).

Records only. Does not validate, execute, or authorize.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from .events import AuditEvent, AuditEventType, utc_now_iso
from .flags import audit_enabled_from_env
from .redact import redact_value
from .storage import AppendOnlyLogAdapter, AuditStorageAdapter

_SCHEMA = "cora.audit.engine.v1"


def default_audit_path() -> Path:
    import os

    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().parent / "audit.log"
    return Path.home() / ".config" / "jarvis" / "audit.log"


class AuditEngine:
    """
    Append-only audit black box.

    `enqueue()` is the preferred Gateway call site — currently drains synchronously
    but the queue API allows a future async worker without changing callers.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        storage: AuditStorageAdapter | None = None,
        path: Path | str | None = None,
    ) -> None:
        self._enabled = audit_enabled_from_env() if enabled is None else bool(enabled)
        self._storage = storage or AppendOnlyLogAdapter(path or default_audit_path())
        self._lock = threading.RLock()
        self._queue: deque[AuditEvent] = deque()
        self._listener: Callable[[AuditEvent], None] | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def append(
        self,
        *,
        event_type: AuditEventType | str,
        request_id: str,
        status: str = "ok",
        session_id: str | None = None,
        owner_id: str | None = None,
        workspace_id: str | None = None,
        intent_id: str | None = None,
        source: str | None = None,
        capability: str | None = None,
        risk_level: str | None = None,
        duration_ms: float | None = None,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent | None:
        """Direct append (still goes through redaction). Prefer enqueue() from Gateway."""
        if not self._enabled:
            return None
        et = event_type if isinstance(event_type, AuditEventType) else AuditEventType(str(event_type))
        event = AuditEvent(
            event_id=f"aev_{uuid.uuid4().hex}",
            timestamp=utc_now_iso(),
            session_id=session_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
            request_id=request_id,
            intent_id=intent_id,
            event_type=et,
            status=status,
            source=source,
            capability=capability,
            risk_level=risk_level,
            duration_ms=duration_ms,
            result=redact_value(dict(result or {})),
            metadata=redact_value(dict(metadata or {})),
        )
        with self._lock:
            self._storage.append(event)
            if self._listener is not None:
                self._listener(event)
        return event

    def enqueue(self, **kwargs: Any) -> AuditEvent | None:
        """Queue seam — currently sync drain; API ready for async worker."""
        if not self._enabled:
            return None
        # Build without writing, then queue + flush.
        # Reuse append path for consistency.
        return self.append(**kwargs)

    def flush(self) -> int:
        """Drain queued events (no-op while enqueue==append sync). Future async hook."""
        with self._lock:
            n = len(self._queue)
            while self._queue:
                ev = self._queue.popleft()
                self._storage.append(ev)
            return n

    def for_request(self, request_id: str) -> list[AuditEvent]:
        """Reconstruct full flow for a request_id (read-only)."""
        with self._lock:
            return [e for e in self._storage.read_all() if e.request_id == request_id]

    def read_all(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._storage.read_all())

    # Convenience emitters prepared for 1E
    def emit_estop_triggered(self, request_id: str, **kwargs: Any) -> AuditEvent | None:
        return self.enqueue(
            event_type=AuditEventType.ESTOP_TRIGGERED,
            request_id=request_id,
            status="triggered",
            **kwargs,
        )

    def emit_estop_released(self, request_id: str, **kwargs: Any) -> AuditEvent | None:
        return self.enqueue(
            event_type=AuditEventType.ESTOP_RELEASED,
            request_id=request_id,
            status="released",
            **kwargs,
        )


_ENGINE: AuditEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_audit_engine(
    *,
    enabled: bool | None = None,
    path: Path | str | None = None,
) -> AuditEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = AuditEngine(enabled=enabled, path=path)
        elif enabled is not None:
            _ENGINE.set_enabled(bool(enabled))
        return _ENGINE


def reset_audit_engine_for_tests() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None
