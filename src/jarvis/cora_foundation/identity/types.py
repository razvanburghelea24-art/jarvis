"""Pure identity types — no business logic, no I/O, no side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AccessLevel(str, Enum):
    """Coarse access levels stored on Owner Identity (not Discord role resolution)."""

    GUEST = "guest"
    OPERATOR = "operator"
    OWNER = "owner"


class SessionState(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    ERROR = "Error"
    STOPPED = "Stopped"


class WorkspaceMode(str, Enum):
    DEV = "Dev"
    REVIEW = "Review"
    PRODUCTION = "Production"


@dataclass(frozen=True)
class OwnerIdentity:
    """Who the Owner is — identifiers and access metadata only."""

    owner_id: str
    access_level: AccessLevel = AccessLevel.OWNER
    roles: tuple[str, ...] = ()
    preferences: Mapping[str, str] = field(default_factory=dict)
    # Reference id for an internal auth key — NEVER the secret material itself.
    auth_key_id: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "access_level": self.access_level.value,
            "roles": list(self.roles),
            "preferences": dict(self.preferences),
            "auth_key_id": self.auth_key_id,
        }


@dataclass(frozen=True)
class SessionIdentity:
    """Active session — ids and state only (no conversation content)."""

    session_id: str
    owner_id: str | None = None
    conversation_context_id: str | None = None
    active_runtime_id: str | None = None
    state: SessionState = SessionState.IDLE

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "conversation_context_id": self.conversation_context_id,
            "active_runtime_id": self.active_runtime_id,
            "state": self.state.value,
        }


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Where code/work is happening — paths and git refs only."""

    workspace_id: str
    path: str | None = None
    repository: str | None = None
    branch: str | None = None
    head: str | None = None
    mode: WorkspaceMode = WorkspaceMode.DEV

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "path": self.path,
            "repository": self.repository,
            "branch": self.branch,
            "head": self.head,
            "mode": self.mode.value,
        }


@dataclass(frozen=True)
class RuntimeIdentity:
    """Who/what this Core process is right now."""

    runtime_id: str
    core_name: str = "cora-core"
    version: str = "0.0.0"
    build: str = "dev"
    capabilities: tuple[str, ...] = ()
    current_state: str = "Idle"
    safe_mode: bool = False
    e_stop: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "core_name": self.core_name,
            "version": self.version,
            "build": self.build,
            "capabilities": list(self.capabilities),
            "current_state": self.current_state,
            "safe_mode": self.safe_mode,
            "e_stop": self.e_stop,
        }
