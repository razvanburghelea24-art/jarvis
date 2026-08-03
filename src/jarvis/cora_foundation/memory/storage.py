"""Storage adapter — single backend behind Memory Engine.

Phase 1B ships one JSON-file adapter (one file = one SSOT blob).
SQLite/other backends can replace the adapter later without changing callers.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .records import MemoryRecord


class MemoryStorageAdapter(ABC):
    """Only the Memory Engine may call these methods (dual-write forbidden)."""

    @abstractmethod
    def load_all(self) -> dict[str, MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def save_all(self, records: dict[str, MemoryRecord], *, meta: dict[str, Any]) -> None:
        raise NotImplementedError


class JsonStorageAdapter(MemoryStorageAdapter):
    """Single JSON document on disk — reconstructable after restart."""

    SCHEMA = "cora.memory.ssot.v1"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load_all(self) -> dict[str, MemoryRecord]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        items = raw.get("records") or {}
        out: dict[str, MemoryRecord] = {}
        if isinstance(items, dict):
            for key, val in items.items():
                if isinstance(val, dict):
                    out[str(key)] = MemoryRecord.from_dict(val)
        return out

    def save_all(self, records: dict[str, MemoryRecord], *, meta: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "schema": self.SCHEMA,
            "meta": dict(meta),
            "records": {rid: rec.to_dict() for rid, rec in records.items()},
        }
        data = json.dumps(blob, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        # Atomic replace — one writer path only.
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
