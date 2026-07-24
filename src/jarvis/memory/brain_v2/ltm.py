"""Long-Term Memory — durable facts (skeleton)."""

from __future__ import annotations

from typing import Optional, Sequence

from ._store import InMemoryStore
from .types import MemoryKind, MemoryRecord, MemoryStatus


class LongTermMemoryStub:
    """Stub for persistent facts. Future: StateStore / Owner Profile bridge."""

    kind = MemoryKind.LONG_TERM

    def __init__(self) -> None:
        self._store = InMemoryStore(MemoryKind.LONG_TERM)

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

    def confirm(self, record_id: str) -> Optional[MemoryRecord]:
        rec = self.get(record_id)
        if rec is None:
            return None
        confirmed = rec.with_status(MemoryStatus.ACTIVE)
        return self.put(confirmed)
