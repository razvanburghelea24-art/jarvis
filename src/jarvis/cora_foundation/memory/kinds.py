"""Memory kinds and task status — data labels only, no business logic."""

from __future__ import annotations

from enum import Enum


class MemoryKind(str, Enum):
    OWNER = "owner"
    SESSION = "session"
    WORKSPACE = "workspace"
    RUNTIME = "runtime"
    TASK = "task"


class TaskStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    TESTING = "TESTING"
    REVIEW = "REVIEW"
    WAITING_OWNER = "WAITING_OWNER"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"
