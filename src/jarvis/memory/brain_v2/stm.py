"""Short-Term Memory — current conversation buffer (skeleton)."""

from __future__ import annotations

from typing import Optional, Sequence

from ._store import InMemoryStore
from .types import MemoryKind, MemoryRecord, MemoryScope, MemoryStatus


class ShortTermMemoryStub:
    """In-process rolling buffer. Future: adapter over DialogueMemory."""

    kind = MemoryKind.SHORT_TERM

    def __init__(self, *, max_turns: int = 64) -> None:
        self._store = InMemoryStore(MemoryKind.SHORT_TERM, max_records=max_turns)
        self.max_turns = max_turns

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
        return self._store.hard_delete(record_id)

    def clear(self) -> None:
        self._store.clear()

    def append_turn(
        self,
        role: str,
        text: str,
        *,
        session_id: Optional[str] = None,
    ) -> MemoryRecord:
        rec = MemoryRecord(
            kind=MemoryKind.SHORT_TERM,
            content=text,
            status=MemoryStatus.ACTIVE,
            scope=MemoryScope.SESSION,
            source=f"turn:{role}",
            session_id=session_id,
            payload={"role": role},
        )
        return self.put(rec)

    def recent(self, *, limit: int = 20) -> Sequence[MemoryRecord]:
        return self._store.search("", limit=limit, status=MemoryStatus.ACTIVE)
