"""Gateway audit bridge — records pipeline markers and forwards to AuditEngine.

Does not authorize or execute. Durable persistence only when AuditEngine is enabled.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..audit import AuditEngine, AuditEventType


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    """Lightweight in-process marker (Gateway tests / ephemeral trail)."""

    event_type: str
    command_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=_now)


class AuditJournal:
    """Append-only in-process journal + optional durable AuditEngine forward."""

    REQUEST_RECEIVED = AuditEventType.REQUEST_RECEIVED.value
    REQUEST_NORMALIZED = AuditEventType.REQUEST_NORMALIZED.value
    IDENTITY_RESOLVED = AuditEventType.IDENTITY_RESOLVED.value
    MEMORY_RESOLVED = AuditEventType.MEMORY_RESOLVED.value
    INTENT_CLASSIFIED = AuditEventType.INTENT_CLASSIFIED.value
    POLICY_EVALUATED = AuditEventType.POLICY_EVALUATED.value
    PLAN_CREATED = AuditEventType.PLAN_CREATED.value
    DISPATCH_STARTED = AuditEventType.DISPATCH_STARTED.value
    DISPATCH_COMPLETED = AuditEventType.DISPATCH_COMPLETED.value
    REQUEST_COMPLETED = AuditEventType.REQUEST_COMPLETED.value
    REQUEST_FAILED = AuditEventType.REQUEST_FAILED.value
    SAFE_MODE_BLOCK = AuditEventType.SAFE_MODE_BLOCK.value
    ESTOP_BLOCK = AuditEventType.ESTOP_BLOCK.value
    ESTOP_TRIGGERED = AuditEventType.ESTOP_TRIGGERED.value
    ESTOP_RELEASED = AuditEventType.ESTOP_RELEASED.value

    def __init__(self, engine: AuditEngine | None = None) -> None:
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []
        self._engine = engine

    def bind_engine(self, engine: AuditEngine | None) -> None:
        self._engine = engine

    def emit(
        self,
        event_type: str,
        command_id: str,
        *,
        session_id: str | None = None,
        owner_id: str | None = None,
        workspace_id: str | None = None,
        intent_id: str | None = None,
        source: str | None = None,
        capability: str | None = None,
        risk_level: str | None = None,
        duration_ms: float | None = None,
        status: str = "ok",
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        meta = dict(metadata or {})
        payload = dict(meta)
        if result is not None:
            payload["result"] = result
        ev = AuditEvent(event_type=event_type, command_id=command_id, payload=payload, at=_now())
        with self._lock:
            self._events.append(ev)
        if self._engine is not None and self._engine.enabled:
            try:
                et = AuditEventType(event_type)
            except ValueError:
                et = AuditEventType.REQUEST_FAILED
            self._engine.enqueue(
                event_type=et,
                request_id=command_id,
                status=status,
                session_id=session_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                intent_id=intent_id,
                source=source,
                capability=capability,
                risk_level=risk_level,
                duration_ms=duration_ms,
                result=result,
                metadata=meta,
            )
        return ev

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def clear_for_tests(self) -> None:
        with self._lock:
            self._events.clear()
