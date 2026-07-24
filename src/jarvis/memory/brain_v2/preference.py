"""Preference Memory — propose/confirm local preferences (Brain Memory v2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .models import (
    PreferenceMemoryRecord,
    empty_preferences_document,
    normalize_preference_key,
    utc_now_iso,
)
from .persistence import BrainV2JsonStore
from .types import MemoryKind, MemoryRecord, MemoryStatus

__all__ = ["PreferenceMemory", "PreferenceMemoryStub"]


class PreferenceMemory:
    """Key/value preferences with explicit confirmation.

    ``propose`` never confirms. Only ``confirm`` marks a preference
    authoritative for future consumers. No auto-learning.
    """

    kind = MemoryKind.PREFERENCE

    def __init__(self, store: Optional[BrainV2JsonStore] = None) -> None:
        self._store = store or BrainV2JsonStore(
            path="preferences.json",  # unused when writable=False
            empty_factory=empty_preferences_document,
            writable=False,
        )

    def get(self, key: str) -> Optional[PreferenceMemoryRecord]:
        try:
            k = normalize_preference_key(key)
        except ValueError:
            return None
        items = self._store.snapshot().get("items") or {}
        raw = items.get(k)
        if not isinstance(raw, dict):
            return None
        try:
            return PreferenceMemoryRecord.from_dict(raw)
        except ValueError:
            return None

    def list(self) -> Sequence[PreferenceMemoryRecord]:
        items = self._store.snapshot().get("items") or {}
        out: List[PreferenceMemoryRecord] = []
        for raw in items.values():
            if not isinstance(raw, dict):
                continue
            try:
                out.append(PreferenceMemoryRecord.from_dict(raw))
            except ValueError:
                continue
        out.sort(key=lambda r: r.key)
        return out

    def propose(
        self,
        key: str,
        value: Any,
        *,
        confidence: float = 0.0,
        source: str = "unknown",
    ) -> Optional[PreferenceMemoryRecord]:
        try:
            k = normalize_preference_key(key)
        except ValueError:
            return None
        now = utc_now_iso()
        existing = self.get(k)
        # Re-propose un-confirms until confirm() again.
        if existing is not None:
            rec = PreferenceMemoryRecord(
                key=k,
                value=str(value if value is not None else ""),
                confidence=float(confidence),
                source=str(source or "unknown"),
                confirmed=False,
                created_at=existing.created_at,
                updated_at=now,
            )
        else:
            rec = PreferenceMemoryRecord(
                key=k,
                value=str(value if value is not None else ""),
                confidence=float(confidence),
                source=str(source or "unknown"),
                confirmed=False,
                created_at=now,
                updated_at=now,
            )
        # Re-validate through from_dict for clamps / size limits.
        rec = PreferenceMemoryRecord.from_dict(rec.to_dict())

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items[k] = rec.to_dict()
            doc["updated_at"] = now
            doc.setdefault("schema_version", 1)

        if not self._store.mutate(_mut):
            return None
        return rec

    def confirm(self, key: str) -> Optional[PreferenceMemoryRecord]:
        try:
            k = normalize_preference_key(key)
        except ValueError:
            return None
        existing = self.get(k)
        if existing is None:
            return None
        now = utc_now_iso()
        confirmed = PreferenceMemoryRecord.from_dict(
            {
                **existing.to_dict(),
                "confirmed": True,
                "updated_at": now,
            }
        )

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items[k] = confirmed.to_dict()
            doc["updated_at"] = now

        if not self._store.mutate(_mut):
            return None
        return confirmed

    def reject(self, key: str) -> bool:
        """Drop a preference. Idempotent: missing key still returns True."""
        return self.delete(key)

    def delete(self, key: str) -> bool:
        """Remove a preference key. Idempotent for already-absent keys."""
        try:
            k = normalize_preference_key(key)
        except ValueError:
            return False
        snap = self._store.snapshot().get("items") or {}
        if k not in snap:
            return True
        now = utc_now_iso()

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items.pop(k, None)
            doc["updated_at"] = now

        return self._store.mutate(_mut)

    def clear(self) -> None:
        self._store.replace(empty_preferences_document())

    # --- Protocol bridge (MemoryModule-shaped) for facade smoke tests --------

    def put(self, record: MemoryRecord) -> MemoryRecord:
        if record.kind != MemoryKind.PREFERENCE:
            raise ValueError("preference store rejected non-preference record")
        key = record.payload.get("key") if isinstance(record.payload, dict) else None
        key = key or record.record_id
        proposed = self.propose(
            str(key),
            record.content,
            confidence=record.confidence,
            source=record.source,
        )
        if proposed is None:
            raise RuntimeError("preference propose failed")
        if record.status == MemoryStatus.ACTIVE:
            self.confirm(proposed.key)
        return record

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        status: Optional[MemoryStatus] = None,
    ) -> Sequence[MemoryRecord]:
        q = (query or "").strip().lower()
        out: List[MemoryRecord] = []
        for pref in self.list():
            if status is MemoryStatus.ACTIVE and not pref.confirmed:
                continue
            if status is MemoryStatus.CANDIDATE and pref.confirmed:
                continue
            blob = f"{pref.key} {pref.value}".lower()
            if q and q not in blob:
                continue
            out.append(
                MemoryRecord(
                    kind=MemoryKind.PREFERENCE,
                    content=pref.value,
                    record_id=pref.key,
                    status=MemoryStatus.ACTIVE if pref.confirmed else MemoryStatus.CANDIDATE,
                    confidence=pref.confidence,
                    source=pref.source,
                    payload={"key": pref.key, "confirmed": pref.confirmed},
                )
            )
            if len(out) >= max(1, int(limit)):
                break
        return out

    def forget(self, record_id: str) -> bool:
        return self.delete(record_id)


# Back-compat alias used by older skeleton imports/tests.
PreferenceMemoryStub = PreferenceMemory
