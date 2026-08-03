"""Cora Foundation — Phase 1D Audit (append-only black box).

No validation. No execution. No authorization. Record only.
Default OFF. Dual-write forbidden — only AuditEngine.append.
"""

from .engine import AuditEngine, get_audit_engine, reset_audit_engine_for_tests
from .events import AuditEvent, AuditEventType
from .flags import ENV_ENABLED, audit_enabled_from_env
from .redact import redact_value
from .storage import AppendOnlyLogAdapter, AuditStorageAdapter

__all__ = [
    "ENV_ENABLED",
    "AppendOnlyLogAdapter",
    "AuditEngine",
    "AuditEvent",
    "AuditEventType",
    "AuditStorageAdapter",
    "audit_enabled_from_env",
    "get_audit_engine",
    "redact_value",
    "reset_audit_engine_for_tests",
]
