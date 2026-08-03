"""Cora Foundation — Phase 1A Identity (no business logic).

Independent identity service for Cora Core (Jarvis live).
Default OFF. No Memory / Gateway / tools / Discord / Overlay coupling.
"""

from .service import IdentityService, get_identity_service, reset_identity_service_for_tests
from .snapshot import IdentitySnapshot, whoami
from .types import (
    AccessLevel,
    OwnerIdentity,
    RuntimeIdentity,
    SessionIdentity,
    SessionState,
    WorkspaceIdentity,
    WorkspaceMode,
)

__all__ = [
    "AccessLevel",
    "IdentityService",
    "IdentitySnapshot",
    "OwnerIdentity",
    "RuntimeIdentity",
    "SessionIdentity",
    "SessionState",
    "WorkspaceIdentity",
    "WorkspaceMode",
    "get_identity_service",
    "reset_identity_service_for_tests",
    "whoami",
]
