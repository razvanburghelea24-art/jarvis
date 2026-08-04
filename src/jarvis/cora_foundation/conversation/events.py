"""Conversation event timeline — state transitions only.

No Engine, Planner, LLM, or tool routing. Events are for Timeline / Debug / Audit / Replay.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

EVENT_CONVERSATION_STATE_CHANGED = "ConversationStateChanged"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConversationStateChanged:
    """One presentation/lifecycle transition on the conversation projection."""

    event_type: str
    timestamp: str
    previous_state: str | None
    current_state: str
    request_id: str | None
    workspace_id: str | None
    session_id: str | None = None
    event_id: str = ""
    lifecycle: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id:
            object.__setattr__(self, "event_id", f"cse_{uuid.uuid4().hex[:12]}")
        if self.event_type != EVENT_CONVERSATION_STATE_CHANGED:
            object.__setattr__(self, "event_type", EVENT_CONVERSATION_STATE_CHANGED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "lifecycle": self.lifecycle,
        }


class ConversationEventJournal:
    """Append-only in-process ring buffer of ConversationStateChanged events."""

    def __init__(self, *, capacity: int = 200) -> None:
        self._capacity = max(1, int(capacity))
        self._lock = threading.RLock()
        self._events: list[ConversationStateChanged] = []
        self._last_presentation: str | None = None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_presentation = None

    def record_state(
        self,
        *,
        presentation: str | None,
        request_id: str | None = None,
        workspace_id: str | None = None,
        session_id: str | None = None,
        lifecycle: str | None = None,
        force: bool = False,
    ) -> ConversationStateChanged | None:
        """Emit ConversationStateChanged when presentation changes (or force)."""
        current = presentation
        with self._lock:
            previous = self._last_presentation
            if not force and previous == current:
                return None
            if current is None and previous is None:
                return None
            event = ConversationStateChanged(
                event_type=EVENT_CONVERSATION_STATE_CHANGED,
                timestamp=_now(),
                previous_state=previous,
                current_state=current if current is not None else "Idle",
                request_id=request_id,
                workspace_id=workspace_id,
                session_id=session_id,
                lifecycle=lifecycle,
            )
            self._events.append(event)
            if len(self._events) > self._capacity:
                self._events = self._events[-self._capacity :]
            self._last_presentation = event.current_state
            return event

    def events(self, *, limit: int | None = None) -> list[ConversationStateChanged]:
        with self._lock:
            items = list(self._events)
        if limit is not None:
            return items[-max(0, int(limit)) :]
        return items

    def to_timeline(self, *, limit: int = 40) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events(limit=limit)]


_JOURNAL: ConversationEventJournal | None = None
_JLOCK = threading.Lock()


def get_conversation_event_journal() -> ConversationEventJournal:
    global _JOURNAL
    with _JLOCK:
        if _JOURNAL is None:
            _JOURNAL = ConversationEventJournal()
        return _JOURNAL


def reset_conversation_event_journal_for_tests() -> None:
    global _JOURNAL
    with _JLOCK:
        if _JOURNAL is not None:
            _JOURNAL.clear()
        _JOURNAL = None
