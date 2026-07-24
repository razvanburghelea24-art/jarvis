"""Skill Memory — learned procedures (skeleton; never grants execution)."""

from __future__ import annotations

from typing import Optional, Sequence

from ._store import InMemoryStore
from .types import MemoryKind, MemoryRecord, MemoryStatus


class SkillMemoryStub:
    """Stub for procedural memory. Reading a skill ≠ permission to run tools."""

    kind = MemoryKind.SKILL

    def __init__(self) -> None:
        self._store = InMemoryStore(MemoryKind.SKILL)

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

    def mark_practiced(self, record_id: str) -> Optional[MemoryRecord]:
        rec = self.get(record_id)
        if rec is None:
            return None
        payload = dict(rec.payload)
        payload["practice_count"] = int(payload.get("practice_count", 0)) + 1
        updated = MemoryRecord(
            kind=rec.kind,
            content=rec.content,
            record_id=rec.record_id,
            status=MemoryStatus.ACTIVE,
            scope=rec.scope,
            confidence=rec.confidence,
            source=rec.source,
            session_id=rec.session_id,
            project_id=rec.project_id,
            created_at=rec.created_at,
            payload=payload,
            tags=rec.tags,
        )
        return self.put(updated)
