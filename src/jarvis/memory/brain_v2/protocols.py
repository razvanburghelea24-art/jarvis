"""Internal APIs (Protocols) for each Brain Memory v2 module.

Implementations in this package are stubs. Future durable backends must
honour these contracts without changing call sites.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from .types import MemoryKind, MemoryRecord, MemoryStatus


@runtime_checkable
class MemoryModule(Protocol):
    """Common surface shared by all seven modules."""

    kind: MemoryKind

    def put(self, record: MemoryRecord) -> MemoryRecord:
        """Insert or replace a record. Returns the stored copy."""
        ...

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """Fetch by id, or ``None`` if missing / forgotten."""
        ...

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        status: Optional[MemoryStatus] = None,
    ) -> Sequence[MemoryRecord]:
        """Return relevant records (stub: substring / recency)."""
        ...

    def forget(self, record_id: str) -> bool:
        """Mark forgotten or drop (STM may hard-delete)."""
        ...

    def clear(self) -> None:
        """Module-local reset. Never crosses module boundaries."""
        ...


@runtime_checkable
class ShortTermMemory(MemoryModule, Protocol):
    """Conversation-current buffer (replaces hot DialogueMemory window long-term)."""

    def append_turn(self, role: str, text: str, *, session_id: Optional[str] = None) -> MemoryRecord:
        ...

    def recent(self, *, limit: int = 20) -> Sequence[MemoryRecord]:
        ...


@runtime_checkable
class LongTermMemory(MemoryModule, Protocol):
    """Durable owner/world facts (intersects StateStore / Owner Profile)."""

    def confirm(self, record_id: str) -> Optional[MemoryRecord]:
        ...


@runtime_checkable
class EpisodicMemory(MemoryModule, Protocol):
    """Session-level 'what happened' (intersects diary summaries)."""

    def close_episode(self, session_id: str, summary: str) -> MemoryRecord:
        ...


@runtime_checkable
class SemanticMemory(MemoryModule, Protocol):
    """Extracted knowledge / concepts (intersects graph nodes)."""

    def link(self, left_id: str, right_id: str, relation: str) -> None:
        ...


@runtime_checkable
class SkillMemory(MemoryModule, Protocol):
    """Procedural 'how Cora learned to do X' (never grants execution)."""

    def mark_practiced(self, record_id: str) -> Optional[MemoryRecord]:
        ...


@runtime_checkable
class PreferenceMemory(MemoryModule, Protocol):
    """Owner preferences with confirmation bias (JSON store in v2 vertical slice)."""

    def propose(
        self,
        key: str,
        value: object,
        *,
        confidence: float = 0.0,
        source: str = "unknown",
    ) -> object:
        ...

    def confirm(self, key: str) -> object:
        ...

    def reject(self, key: str) -> bool:
        ...

    def delete(self, key: str) -> bool:
        ...

    def list(self) -> Sequence[object]:
        ...


@runtime_checkable
class ProjectMemory(MemoryModule, Protocol):
    """Active project state / pending steps (never executes)."""

    def create(self, project_id: str, name: str, **kwargs: object) -> object:
        ...

    def set_active(self, project_id: str) -> bool:
        ...

    def get_active(self) -> Optional[str]:
        ...

    def update_status(self, project_id: str, status: str) -> object:
        ...

    def update_next_action(self, project_id: str, next_action: str, **kwargs: object) -> object:
        ...

    def archive(self, project_id: str) -> bool:
        ...

    def set_active_project(self, project_id: str) -> None:
        ...

    def get_active_project(self) -> Optional[str]:
        ...
