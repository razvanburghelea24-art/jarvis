"""Identity snapshot — answers Who / Where / Session / Runtime without other services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import OwnerIdentity, RuntimeIdentity, SessionIdentity, WorkspaceIdentity


@dataclass(frozen=True)
class IdentitySnapshot:
    enabled: bool
    owner: OwnerIdentity | None
    session: SessionIdentity | None
    workspace: WorkspaceIdentity | None
    runtime: RuntimeIdentity | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "owner": None if self.owner is None else self.owner.to_public_dict(),
            "session": None if self.session is None else self.session.to_public_dict(),
            "workspace": None if self.workspace is None else self.workspace.to_public_dict(),
            "runtime": None if self.runtime is None else self.runtime.to_public_dict(),
            # DoD convenience fields
            "who": None if self.owner is None else self.owner.owner_id,
            "where": None if self.workspace is None else {
                "workspace_id": self.workspace.workspace_id,
                "path": self.workspace.path,
                "repository": self.workspace.repository,
                "branch": self.workspace.branch,
                "mode": self.workspace.mode.value,
            },
            "active_session": None if self.session is None else self.session.session_id,
            "who_are_you": None if self.runtime is None else {
                "runtime_id": self.runtime.runtime_id,
                "core_name": self.runtime.core_name,
                "version": self.runtime.version,
                "build": self.runtime.build,
                "current_state": self.runtime.current_state,
                "safe_mode": self.runtime.safe_mode,
                "e_stop": self.runtime.e_stop,
                "capabilities": list(self.runtime.capabilities),
            },
        }


def whoami(service: Any | None = None) -> dict[str, Any]:
    """Standardized answer: Who am I? Where? What session? Who are you (runtime)?"""
    if service is None:
        from .service import get_identity_service
        service = get_identity_service()
    return service.snapshot().to_public_dict()
