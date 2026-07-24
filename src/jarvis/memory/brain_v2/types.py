"""Shared types for Brain Memory v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional
import uuid


class MemoryKind(str, Enum):
    """Seven first-class memory modules in Brain Memory v2."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    SKILL = "skill"
    PREFERENCE = "preference"
    PROJECT = "project"


class MemoryStatus(str, Enum):
    """Lifecycle shared across durable modules (not STM)."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FORGOTTEN = "forgotten"
    QUARANTINED = "quarantined"


class MemoryScope(str, Enum):
    """Who/what a record is about."""

    OWNER = "owner"
    SESSION = "session"
    PROJECT = "project"
    WORLD = "world"
    SYSTEM = "system"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRecord:
    """Canonical envelope for a single memory item.

    Module-specific payloads live in ``payload``. Persistence backends
    MUST treat unknown payload keys as opaque JSON.
    """

    kind: MemoryKind
    content: str
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: MemoryStatus = MemoryStatus.CANDIDATE
    scope: MemoryScope = MemoryScope.OWNER
    confidence: float = 0.0
    source: str = "unknown"
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    payload: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def with_status(self, status: MemoryStatus) -> "MemoryRecord":
        return MemoryRecord(
            kind=self.kind,
            content=self.content,
            record_id=self.record_id,
            status=status,
            scope=self.scope,
            confidence=self.confidence,
            source=self.source,
            session_id=self.session_id,
            project_id=self.project_id,
            created_at=self.created_at,
            updated_at=_utc_now(),
            payload=dict(self.payload),
            tags=self.tags,
        )
