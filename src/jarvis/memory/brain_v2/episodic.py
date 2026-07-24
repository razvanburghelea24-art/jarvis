"""Episodic Memory — session episodes / diary-shaped events (skeleton)."""

from __future__ import annotations

from typing import Optional, Sequence

from ._store import InMemoryStore
from .types import MemoryKind, MemoryRecord, MemoryScope, MemoryStatus


class EpisodicMemoryStub:
    """Stub for 'what happened in a session'. Future: diary summaries bridge."""

    kind = MemoryKind.EPISODIC

    def __init__(self) -> None:
        self._store = InMemoryStore(MemoryKind.EPISODIC)

    def put(self, record: MemoryRecord) -> MemoryRecord:
        return self._store.put(record)

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self._store.get(record_id)

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        status: Optional[MemoryStatus] = None,
    ) -> Sequence[MemoryRecord]:
        return self._store.search(query, limit=limit, status=status)

    def forget(self, record_id: str) -> bool:
        return self._store.forget(record_id)

    def clear(self) -> None:
        self._store.clear()

    def close_episode(self, session_id: str, summary: str) -> MemoryRecord:
        rec = MemoryRecord(
            kind=MemoryKind.EPISODIC,
            content=summary,
            status=MemoryStatus.ACTIVE,
            scope=MemoryScope.SESSION,
            source="episode_close",
            session_id=session_id,
            payload={"closed": True},
        )
        return self.put(rec)
