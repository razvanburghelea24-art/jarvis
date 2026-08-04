"""ConversationEvents — conversation journal emitter (not Audit · not StateEmitter).

Engine emits only. Observers (EventJournal / Harness / Desktop later) listen via on_event.
Does not write Audit, Snapshot, Persona, visual Timeline, or IPC.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..contracts import ConversationRequest
from ..contracts.schema import freeze_mapping

# Conversation journal event types (not UI / Electron / Audit)
REQUEST_ACCEPTED = "REQUEST_ACCEPTED"
REQUEST_VALIDATED = "REQUEST_VALIDATED"
CONTEXT_BUILT = "CONTEXT_BUILT"
DECISION_MADE = "DECISION_MADE"
STATE_EMITTED = "STATE_EMITTED"
RESPONSE_BUILT = "RESPONSE_BUILT"
CONVERSATION_COMPLETED = "CONVERSATION_COMPLETED"
STREAM_STARTED = "STREAM_STARTED"
STREAM_CHUNK = "STREAM_CHUNK"
STREAM_COMPLETED = "STREAM_COMPLETED"
STREAM_CANCELLED = "STREAM_CANCELLED"

PIPELINE_ORDER = (
    REQUEST_ACCEPTED,
    REQUEST_VALIDATED,
    CONTEXT_BUILT,
    DECISION_MADE,
    STATE_EMITTED,
    RESPONSE_BUILT,
    CONVERSATION_COMPLETED,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConversationEvent:
    """One immutable conversation-journal entry."""

    event_id: str
    request_id: str
    workspace_id: str
    session_id: str
    timestamp: str
    type: str
    payload: Mapping[str, Any] = None  # type: ignore[assignment]
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_mapping(self.payload))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


class EventJournal:
    """Append-only conversation EventJournal (observer sink). Not Audit."""

    def __init__(self, *, capacity: int = 500) -> None:
        self._capacity = max(1, int(capacity))
        self._lock = threading.RLock()
        self._events: list[ConversationEvent] = []

    def record(self, event: ConversationEvent) -> ConversationEvent:
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._capacity:
                self._events = self._events[-self._capacity :]
        return event

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def events(self, *, limit: int | None = None) -> list[ConversationEvent]:
        with self._lock:
            items = list(self._events)
        if limit is not None:
            return items[-max(0, int(limit)) :]
        return items

    def types(self, *, request_id: str | None = None) -> list[str]:
        items = self.events()
        if request_id is not None:
            items = [e for e in items if e.request_id == request_id]
        return [e.type for e in items]

    def to_list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events(limit=limit)]


class ConversationEvents:
    """Emit ConversationEvent only. Does not know Desktop / Audit / Snapshot."""

    def __init__(
        self,
        *,
        on_event: Callable[[ConversationEvent], None] | None = None,
    ) -> None:
        self._on_event = on_event

    def emit(
        self,
        event_type: str,
        request: ConversationRequest,
        *,
        payload: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ConversationEvent:
        event = ConversationEvent(
            event_id=f"cev_{uuid4().hex[:12]}",
            request_id=request.request_id,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            timestamp=_now(),
            type=str(event_type),
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
        )
        if self._on_event is not None:
            self._on_event(event)
        return event

    # Named helpers (deterministic spine vocabulary)

    def request_accepted(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(REQUEST_ACCEPTED, request, payload=payload)

    def request_validated(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(REQUEST_VALIDATED, request, payload=payload)

    def context_built(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(CONTEXT_BUILT, request, payload=payload)

    def decision_made(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(DECISION_MADE, request, payload=payload)

    def state_emitted(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(STATE_EMITTED, request, payload=payload)

    def response_built(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(RESPONSE_BUILT, request, payload=payload)

    def conversation_completed(
        self, request: ConversationRequest, **payload: Any
    ) -> ConversationEvent:
        return self.emit(CONVERSATION_COMPLETED, request, payload=payload)

    def stream_started(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(STREAM_STARTED, request, payload=payload)

    def stream_chunk(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(STREAM_CHUNK, request, payload=payload)

    def stream_completed(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(STREAM_COMPLETED, request, payload=payload)

    def stream_cancelled(self, request: ConversationRequest, **payload: Any) -> ConversationEvent:
        return self.emit(STREAM_CANCELLED, request, payload=payload)
