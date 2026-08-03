"""Append-only audit storage adapter.

No update. No delete. Append only.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from .events import AuditEvent


class AuditStorageAdapter(ABC):
    @abstractmethod
    def append(self, event: AuditEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_all(self) -> list[AuditEvent]:
        raise NotImplementedError


class AppendOnlyLogAdapter(AuditStorageAdapter):
    """Newline-delimited JSON log (`audit.log`). Never rewrites prior lines."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        # O_APPEND | binary write — OS-level append; no truncate/rewrite.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        fd = os.open(str(self.path), flags, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def read_all(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        out: list[AuditEvent] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                out.append(AuditEvent.from_dict(json.loads(line)))
        return out
