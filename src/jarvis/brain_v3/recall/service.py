"""Optional bounded in-memory recall cache (default OFF)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional, Tuple


class RecallCache:
    """Read-only TTL cache. Never persists. No sensitive payloads intended."""

    def __init__(self, *, enabled: bool = False, ttl_seconds: float = 30.0, max_entries: int = 64) -> None:
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(query: str, memory_revision: str, **parts: Any) -> str:
        raw = "|".join([query, memory_revision] + [f"{k}={parts[k]}" for k in sorted(parts)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            self.misses += 1
            return None
        item = self._store.get(key)
        if item is None:
            self.misses += 1
            return None
        expires_at, value = item
        if time.time() > expires_at:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        if len(self._store) >= self.max_entries:
            # drop oldest
            oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
            self._store.pop(oldest, None)
        self._store[key] = (time.time() + self.ttl_seconds, value)

    def invalidate(self) -> None:
        self._store.clear()

    def clear(self) -> None:
        self.invalidate()
