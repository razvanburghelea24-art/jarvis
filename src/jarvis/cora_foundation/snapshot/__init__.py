"""Cora Foundation — Phase 8.2 Unified Runtime Snapshot (READ-ONLY).

Single object for UI. UI must not import Identity/Planner/… — only Snapshot.
"""

from .flags import ENV_ENABLED, snapshot_enabled_from_env
from .schema import UnifiedSnapshot, empty_snapshot
from .service import SnapshotService, default_snapshot_path, get_snapshot_service, reset_snapshot_service_for_tests

__all__ = [
    "ENV_ENABLED",
    "SnapshotService",
    "UnifiedSnapshot",
    "default_snapshot_path",
    "empty_snapshot",
    "get_snapshot_service",
    "reset_snapshot_service_for_tests",
    "snapshot_enabled_from_env",
]
