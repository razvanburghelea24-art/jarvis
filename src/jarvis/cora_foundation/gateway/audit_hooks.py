"""Audit event hooks for Phase 1D — in-memory journal only (no persistence yet)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    command_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=_now)


class AuditJournal:
    """Append-only in-process journal. Phase 1D will persist these event types."""

    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_COMPLETED = "REQUEST_COMPLETED"
    REQUEST_FAILED = "REQUEST_FAILED"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []

    def emit(self, event_type: str, command_id: str, **payload: Any) -> AuditEvent:
        ev = AuditEvent(event_type=event_type, command_id=command_id, payload=dict(payload), at=_now())
        with self._lock:
            self._events.append(ev)
        return ev

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def clear_for_tests(self) -> None:
        with self._lock:
            self._events.clear()
