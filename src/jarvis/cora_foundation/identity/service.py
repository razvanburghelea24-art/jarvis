"""IdentityService — fundamental identity store. No business logic.

Default OFF. In-memory only for Phase 1A (optional later persistence is out of scope).
Does not import Memory, Gateway, tools, Discord, Overlay, owner_profile, or daemon.
"""

from __future__ import annotations

import threading
import uuid
from typing import Mapping

from .flags import identity_enabled_from_env
from .snapshot import IdentitySnapshot
from .types import (
    AccessLevel,
    OwnerIdentity,
    RuntimeIdentity,
    SessionIdentity,
    SessionState,
    WorkspaceIdentity,
    WorkspaceMode,
)

_SCHEMA = "cora.identity.v1"
_DEFAULT_CAPABILITIES = ("identity",)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class IdentityService:
    """Process-local identity registry.

    When disabled, mutations are no-ops (except explicit bootstrap for tests)
    and snapshot reports enabled=False with empty identities unless a prior
    bootstrap was performed while enabled.
    """

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._lock = threading.RLock()
        self._enabled = identity_enabled_from_env() if enabled is None else bool(enabled)
        self._owner: OwnerIdentity | None = None
        self._session: SessionIdentity | None = None
        self._workspace: WorkspaceIdentity | None = None
        self._runtime: RuntimeIdentity | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    # ── Owner ────────────────────────────────────────────────────────────

    def ensure_owner(
        self,
        *,
        owner_id: str | None = None,
        access_level: AccessLevel = AccessLevel.OWNER,
        roles: tuple[str, ...] | list[str] = (),
        preferences: Mapping[str, str] | None = None,
        auth_key_id: str | None = None,
    ) -> OwnerIdentity | None:
        """Create or return Owner Identity. No-op when disabled."""
        with self._lock:
            if not self._enabled:
                return None
            if self._owner is not None and owner_id is None:
                return self._owner
            oid = owner_id or _new_id("own")
            if self._owner is not None and self._owner.owner_id == oid:
                return self._owner
            self._owner = OwnerIdentity(
                owner_id=oid,
                access_level=access_level,
                roles=tuple(roles),
                preferences=dict(preferences or {}),
                auth_key_id=auth_key_id or _new_id("akey"),
            )
            return self._owner

    def get_owner(self) -> OwnerIdentity | None:
        with self._lock:
            return self._owner

    # ── Session ──────────────────────────────────────────────────────────

    def start_session(
        self,
        *,
        session_id: str | None = None,
        owner_id: str | None = None,
        conversation_context_id: str | None = None,
        state: SessionState = SessionState.IDLE,
    ) -> SessionIdentity | None:
        with self._lock:
            if not self._enabled:
                return None
            sid = session_id or _new_id("ses")
            oid = owner_id
            if oid is None and self._owner is not None:
                oid = self._owner.owner_id
            rid = None if self._runtime is None else self._runtime.runtime_id
            self._session = SessionIdentity(
                session_id=sid,
                owner_id=oid,
                conversation_context_id=conversation_context_id or _new_id("ctx"),
                active_runtime_id=rid,
                state=state,
            )
            return self._session

    def set_session_state(self, state: SessionState) -> SessionIdentity | None:
        with self._lock:
            if not self._enabled or self._session is None:
                return None
            self._session = SessionIdentity(
                session_id=self._session.session_id,
                owner_id=self._session.owner_id,
                conversation_context_id=self._session.conversation_context_id,
                active_runtime_id=self._session.active_runtime_id,
                state=state,
            )
            return self._session

    def get_session(self) -> SessionIdentity | None:
        with self._lock:
            return self._session

    # ── Workspace ────────────────────────────────────────────────────────

    def set_workspace(
        self,
        *,
        workspace_id: str | None = None,
        path: str | None = None,
        repository: str | None = None,
        branch: str | None = None,
        head: str | None = None,
        mode: WorkspaceMode = WorkspaceMode.DEV,
    ) -> WorkspaceIdentity | None:
        with self._lock:
            if not self._enabled:
                return None
            wid = workspace_id or _new_id("ws")
            self._workspace = WorkspaceIdentity(
                workspace_id=wid,
                path=path,
                repository=repository,
                branch=branch,
                head=head,
                mode=mode,
            )
            return self._workspace

    def get_workspace(self) -> WorkspaceIdentity | None:
        with self._lock:
            return self._workspace

    # ── Runtime ──────────────────────────────────────────────────────────

    def ensure_runtime(
        self,
        *,
        runtime_id: str | None = None,
        version: str = "0.0.0-foundation-1a",
        build: str = "dev",
        capabilities: tuple[str, ...] | list[str] | None = None,
        current_state: str = "Idle",
        safe_mode: bool = False,
        e_stop: bool = False,
    ) -> RuntimeIdentity | None:
        with self._lock:
            if not self._enabled:
                return None
            if self._runtime is not None and runtime_id is None:
                return self._runtime
            rid = runtime_id or _new_id("rt")
            caps = tuple(capabilities) if capabilities is not None else _DEFAULT_CAPABILITIES
            self._runtime = RuntimeIdentity(
                runtime_id=rid,
                core_name="cora-core",
                version=version,
                build=build,
                capabilities=caps,
                current_state=current_state,
                safe_mode=safe_mode,
                e_stop=e_stop,
            )
            if self._session is not None:
                self._session = SessionIdentity(
                    session_id=self._session.session_id,
                    owner_id=self._session.owner_id,
                    conversation_context_id=self._session.conversation_context_id,
                    active_runtime_id=rid,
                    state=self._session.state,
                )
            return self._runtime

    def set_runtime_flags(self, *, safe_mode: bool | None = None, e_stop: bool | None = None,
                          current_state: str | None = None) -> RuntimeIdentity | None:
        """Update Safe Mode / E-Stop / state flags only — no stop logic here (that is 1E)."""
        with self._lock:
            if not self._enabled or self._runtime is None:
                return None
            self._runtime = RuntimeIdentity(
                runtime_id=self._runtime.runtime_id,
                core_name=self._runtime.core_name,
                version=self._runtime.version,
                build=self._runtime.build,
                capabilities=self._runtime.capabilities,
                current_state=self._runtime.current_state if current_state is None else current_state,
                safe_mode=self._runtime.safe_mode if safe_mode is None else bool(safe_mode),
                e_stop=self._runtime.e_stop if e_stop is None else bool(e_stop),
            )
            return self._runtime

    def get_runtime(self) -> RuntimeIdentity | None:
        with self._lock:
            return self._runtime

    # ── Bootstrap + snapshot ─────────────────────────────────────────────

    def bootstrap_minimal(self) -> IdentitySnapshot:
        """Ensure owner + runtime + session + workspace ids exist (when enabled)."""
        with self._lock:
            if not self._enabled:
                return self.snapshot()
            self.ensure_runtime()
            self.ensure_owner()
            if self._workspace is None:
                self.set_workspace(path=None, mode=WorkspaceMode.DEV)
            if self._session is None:
                self.start_session()
            return self.snapshot()

    def snapshot(self) -> IdentitySnapshot:
        with self._lock:
            return IdentitySnapshot(
                enabled=self._enabled,
                owner=self._owner,
                session=self._session,
                workspace=self._workspace,
                runtime=self._runtime,
            )

    def schema_version(self) -> str:
        return _SCHEMA


_SERVICE: IdentityService | None = None
_SERVICE_LOCK = threading.Lock()


def get_identity_service(*, enabled: bool | None = None) -> IdentityService:
    """Process singleton. Pass enabled= for tests; production reads env default OFF."""
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = IdentityService(enabled=enabled)
        elif enabled is not None and _SERVICE.enabled != bool(enabled):
            _SERVICE.set_enabled(bool(enabled))
        return _SERVICE


def reset_identity_service_for_tests() -> None:
    """Drop singleton — tests only."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = None
