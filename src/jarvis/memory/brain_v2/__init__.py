"""Cora Brain Memory v2 — modular memory architecture.

This package is **inert by default**. Preference + Project have a durable
JSON vertical slice; other modules remain in-memory stubs. Nothing here is
wired into ``reply.engine``, the daemon, audio, Security Center, or
internet research unless ``brain_memory_v2_enabled`` is on *and* a future
integration step opts in.

See ``ARCHITECTURE.md``.
"""

from __future__ import annotations

from .facade import BrainMemoryV2, create_brain_memory_v2
from .models import PreferenceMemoryRecord, ProjectMemoryRecord
from .preference import PreferenceMemory as PreferenceMemoryStore
from .project import ProjectMemory as ProjectMemoryStore
from .protocols import (
    EpisodicMemory,
    LongTermMemory,
    PreferenceMemory,
    ProjectMemory,
    SemanticMemory,
    ShortTermMemory,
    SkillMemory,
)
from .types import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
)

__all__ = [
    "BrainMemoryV2",
    "create_brain_memory_v2",
    "EpisodicMemory",
    "LongTermMemory",
    "PreferenceMemory",
    "PreferenceMemoryRecord",
    "PreferenceMemoryStore",
    "ProjectMemory",
    "ProjectMemoryRecord",
    "ProjectMemoryStore",
    "SemanticMemory",
    "ShortTermMemory",
    "SkillMemory",
    "MemoryKind",
    "MemoryRecord",
    "MemoryScope",
    "MemoryStatus",
]
