"""Semantic Memory — extracted knowledge / concepts (skeleton)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ._store import InMemoryStore
from .types import MemoryKind, MemoryRecord, MemoryStatus


class SemanticMemoryStub:
    """Stub for concept graph. Future: GraphMemoryStore bridge."""

    kind = MemoryKind.SEMANTIC

    def __init__(self) -> None:
        self._store = InMemoryStore(MemoryKind.SEMANTIC)
        self._links: List[Tuple[str, str, str]] = []

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
        self._links.clear()

    def link(self, left_id: str, right_id: str, relation: str) -> None:
        self._links.append((left_id, right_id, relation))

    def links(self) -> Sequence[Tuple[str, str, str]]:
        return tuple(self._links)
