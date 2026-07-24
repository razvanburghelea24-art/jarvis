"""In-memory stub store shared by Brain Memory v2 modules (no persistence yet)."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence

from .types import MemoryKind, MemoryRecord, MemoryStatus


class InMemoryStore:
    """Thread-safe dict backend for skeleton tests and dry-runs."""

    def __init__(self, kind: MemoryKind, *, max_records: int = 10_000) -> None:
        self.kind = kind
        self.max_records = max(1, int(max_records))
        self._lock = threading.RLock()
        self._items: Dict[str, MemoryRecord] = {}
        self._order: List[str] = []

    def put(self, record: MemoryRecord) -> MemoryRecord:
        if record.kind != self.kind:
            raise ValueError(
                f"{self.kind.value} store rejected record of kind {record.kind.value}"
            )
        with self._lock:
            if record.record_id not in self._items:
                self._order.append(record.record_id)
            self._items[record.record_id] = record
            while len(self._order) > self.max_records:
                old = self._order.pop(0)
                self._items.pop(old, None)
            return record

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            rec = self._items.get(record_id)
            if rec is None:
                return None
            if rec.status == MemoryStatus.FORGOTTEN:
                return None
            return rec

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        status: Optional[MemoryStatus] = None,
    ) -> Sequence[MemoryRecord]:
        q = (query or "").strip().lower()
        limit = max(1, int(limit))
        with self._lock:
            out: List[MemoryRecord] = []
            for rid in reversed(self._order):
                rec = self._items.get(rid)
                if rec is None or rec.status == MemoryStatus.FORGOTTEN:
                    continue
                if status is not None and rec.status != status:
                    continue
                if q and q not in rec.content.lower():
                    continue
                out.append(rec)
                if len(out) >= limit:
                    break
            return out

    def forget(self, record_id: str) -> bool:
        with self._lock:
            rec = self._items.get(record_id)
            if rec is None:
                return False
            self._items[record_id] = rec.with_status(MemoryStatus.FORGOTTEN)
            return True

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._order.clear()

    def hard_delete(self, record_id: str) -> bool:
        with self._lock:
            if record_id not in self._items:
                return False
            del self._items[record_id]
            self._order = [r for r in self._order if r != record_id]
            return True
