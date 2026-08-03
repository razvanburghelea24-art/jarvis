"""Cora Foundation — Phase 1B Memory SSOT.

One memory. One API. One storage adapter instance.
Dual-write forbidden. Default OFF.
"""

from .engine import MemoryEngine, get_memory_engine, reset_memory_engine_for_tests
from .flags import ENV_ENABLED, memory_enabled_from_env
from .kinds import MemoryKind, TaskStatus
from .records import MemoryRecord, TaskPayload
from .storage import JsonStorageAdapter, MemoryStorageAdapter

__all__ = [
    "ENV_ENABLED",
    "JsonStorageAdapter",
    "MemoryEngine",
    "MemoryKind",
    "MemoryRecord",
    "MemoryStorageAdapter",
    "TaskPayload",
    "TaskStatus",
    "get_memory_engine",
    "memory_enabled_from_env",
    "reset_memory_engine_for_tests",
]
