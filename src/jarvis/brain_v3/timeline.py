"""Timeline service for Brain V3 Phase 1."""

from __future__ import annotations

import sqlite3
from typing import Any, List, Mapping, Optional, Set

from .errors import LimitExceededError, ValidationError
from .limits import BrainV3Limits
from .models import TimelineEvent, content_hash, dumps_json, utc_now_iso
from .validation import build_timeline_event


def timeline_dedupe_hash(
    event_type: str,
    title: str,
    occurred_at: str,
    entity_ids: List[str],
) -> str:
    """Deterministic dedupe hash aligned with repository storage."""
    payload = dumps_json(
        {
            "event_type": event_type,
            "title": title,
            "occurred_at": occurred_at,
            "entity_ids": sorted(entity_ids),
        }
    )
    return content_hash(payload)


def _sort_events(events: List[TimelineEvent]) -> List[TimelineEvent]:
    return sorted(events, key=lambda event: (event.occurred_at, event.id))


def _filter_events(
    events: List[TimelineEvent],
    *,
    entity_id: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> List[TimelineEvent]:
    filtered: List[TimelineEvent] = []
    for event in events:
        if entity_id is not None and entity_id not in event.entity_ids:
            continue
        if time_from is not None and event.occurred_at < time_from:
            continue
        if time_to is not None and event.occurred_at > time_to:
            continue
        filtered.append(event)
    return filtered


class TimelineService:
    """Bounded, deterministic timeline operations."""

    def __init__(self, repo: Any, limits: BrainV3Limits | None = None) -> None:
        self._repo = repo
        self._limits = limits or BrainV3Limits()

    def _ensure_writable(self) -> None:
        if getattr(self._repo, "read_only", False):
            raise ValidationError("repository is read-only")

    def record_event(self, data: Mapping[str, Any]) -> TimelineEvent:
        self._ensure_writable()
        if self._repo.count_timeline_events() >= self._limits.max_timeline_events:
            raise LimitExceededError("max_timeline_events exceeded")
        event = build_timeline_event(data, self._limits)
        dedupe = timeline_dedupe_hash(
            event.event_type,
            event.title,
            event.occurred_at,
            event.entity_ids,
        )
        for entity_id in event.entity_ids:
            self._repo.get_entity(entity_id)
        existing = self._find_by_dedupe(dedupe)
        if existing is not None:
            return existing
        try:
            return self._repo.create_timeline_event(event)
        except sqlite3.IntegrityError:
            existing = self._find_by_dedupe(dedupe)
            if existing is not None:
                return existing
            raise

    def _find_by_dedupe(self, dedupe: str) -> Optional[TimelineEvent]:
        for event in self._repo.list_timeline_events(limit=self._limits.max_batch_size):
            candidate = timeline_dedupe_hash(
                event.event_type,
                event.title,
                event.occurred_at,
                event.entity_ids,
            )
            if candidate == dedupe:
                return event
        return None

    def get_event(self, event_id: str) -> TimelineEvent:
        return self._repo.get_timeline_event(event_id)

    def list_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        entity_id: Optional[str] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> List[TimelineEvent]:
        bounded = min(max(1, limit), self._limits.max_batch_size)
        events = self._repo.list_timeline_events(limit=self._limits.max_batch_size, offset=0)
        events = _filter_events(events, entity_id=entity_id, time_from=time_from, time_to=time_to)
        events = _sort_events(events)
        start = max(0, offset)
        return events[start : start + bounded]

    def events_for_entity(
        self,
        entity_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TimelineEvent]:
        self._repo.get_entity(entity_id)
        return self.list_events(limit=limit, offset=offset, entity_id=entity_id)

    def events_between_dates(
        self,
        time_from: str,
        time_to: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TimelineEvent]:
        return self.list_events(
            limit=limit,
            offset=offset,
            time_from=time_from,
            time_to=time_to,
        )

    def latest_events(self, *, limit: int = 20) -> List[TimelineEvent]:
        bounded = min(max(1, limit), self._limits.max_batch_size)
        events = self._repo.list_timeline_events(limit=bounded, offset=0)
        return _sort_events(events)[-bounded:]

    def project_timeline(
        self,
        project_entity_id: str,
        *,
        limit: int = 200,
    ) -> List[TimelineEvent]:
        """Timeline for a project and entities related within one hop."""
        self._repo.get_entity(project_entity_id)
        entity_ids: Set[str] = {project_entity_id}
        for neighbor, relation in self._repo.neighbors(project_entity_id, limit=self._limits.max_batch_size):
            if relation.status == "active":
                entity_ids.add(neighbor.id)
        events: List[TimelineEvent] = []
        for event in self._repo.list_timeline_events(limit=self._limits.max_batch_size):
            if any(eid in entity_ids for eid in event.entity_ids):
                events.append(event)
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return _sort_events(events)[:bounded]
