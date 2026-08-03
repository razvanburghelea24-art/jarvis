"""MemoryEngine — the only write path into Cora Memory SSOT.

Law: Dual-write forbidden. Components must call this API only.
No Discord/Overlay/n8n/Desktop side stores.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any, Iterable

from .flags import memory_enabled_from_env
from .kinds import MemoryKind, TaskStatus
from .records import MemoryRecord, TaskPayload, utc_now_iso
from .storage import JsonStorageAdapter, MemoryStorageAdapter

_SCHEMA = "cora.memory.engine.v1"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def default_memory_path() -> Path:
    """Single SSOT file under ~/.config/jarvis (or JARVIS_CONFIG_PATH parent)."""
    import os

    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().parent / "cora_memory_ssot.json"
    return Path.home() / ".config" / "jarvis" / "cora_memory_ssot.json"


class MemoryEngine:
    """In-process memory SSOT backed by one StorageAdapter."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        storage: MemoryStorageAdapter | None = None,
        path: Path | str | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._enabled = memory_enabled_from_env() if enabled is None else bool(enabled)
        if storage is not None:
            self._storage = storage
        else:
            self._storage = JsonStorageAdapter(path or default_memory_path())
        self._records: dict[str, MemoryRecord] = {}
        self._revision: int = 0  # global blob revision (versioned store)
        self._loaded = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    # ── load / persist ───────────────────────────────────────────────────

    def load(self) -> int:
        """Reconstruct memory from storage (restart recovery)."""
        with self._lock:
            if not self._enabled:
                self._records = {}
                self._revision = 0
                self._loaded = True
                return 0
            self._records = self._storage.load_all()
            self._revision = max((r.version for r in self._records.values()), default=0)
            self._loaded = True
            return len(self._records)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _persist(self) -> None:
        self._storage.save_all(
            self._records,
            meta={
                "schema": _SCHEMA,
                "revision": self._revision,
                "updated_at": utc_now_iso(),
                "record_count": len(self._records),
            },
        )

    # ── generic CRUD ─────────────────────────────────────────────────────

    def upsert(
        self,
        *,
        kind: MemoryKind,
        payload: dict[str, Any],
        record_id: str | None = None,
        owner_id: str | None = None,
    ) -> MemoryRecord | None:
        with self._lock:
            if not self._enabled:
                return None
            self._ensure_loaded()
            now = utc_now_iso()
            rid = record_id or _new_id(kind.value[:3])
            existing = self._records.get(rid)
            if existing is not None:
                version = int(existing.version) + 1
                created = existing.created_at
            else:
                version = 1
                created = now
            rec = MemoryRecord(
                record_id=rid,
                kind=kind,
                version=version,
                created_at=created,
                updated_at=now,
                payload=dict(payload),
                owner_id=owner_id,
            )
            self._records[rid] = rec
            self._revision += 1
            self._persist()
            return rec

    def get(self, record_id: str) -> MemoryRecord | None:
        with self._lock:
            if not self._enabled:
                return None
            self._ensure_loaded()
            return self._records.get(record_id)

    def list(self, kind: MemoryKind | None = None) -> list[MemoryRecord]:
        with self._lock:
            if not self._enabled:
                return []
            self._ensure_loaded()
            vals = list(self._records.values())
            if kind is not None:
                vals = [r for r in vals if r.kind == kind]
            vals.sort(key=lambda r: r.updated_at, reverse=True)
            return vals

    def delete(self, record_id: str) -> bool:
        """Soft-delete via tombstone version bump (payload cleared, kind kept)."""
        with self._lock:
            if not self._enabled:
                return False
            self._ensure_loaded()
            existing = self._records.get(record_id)
            if existing is None:
                return False
            now = utc_now_iso()
            self._records[record_id] = MemoryRecord(
                record_id=existing.record_id,
                kind=existing.kind,
                version=int(existing.version) + 1,
                created_at=existing.created_at,
                updated_at=now,
                payload={"_deleted": True},
                owner_id=existing.owner_id,
            )
            self._revision += 1
            self._persist()
            return True

    # ── domain helpers (still no business logic — structured payloads only) ─

    def put_owner_memory(
        self,
        *,
        owner_id: str,
        profile: dict[str, Any] | None = None,
        projects: list[Any] | None = None,
        preferences: dict[str, str] | None = None,
        rules: list[str] | None = None,
        record_id: str | None = None,
    ) -> MemoryRecord | None:
        payload = {
            "profile": dict(profile or {}),
            "projects": list(projects or []),
            "preferences": dict(preferences or {}),
            "rules": list(rules or []),
        }
        return self.upsert(
            kind=MemoryKind.OWNER,
            payload=payload,
            record_id=record_id or f"owner_{owner_id}",
            owner_id=owner_id,
        )

    def put_session_memory(
        self,
        *,
        session_id: str,
        conversation: list[Any] | None = None,
        current_task_id: str | None = None,
        active_context: dict[str, Any] | None = None,
        owner_id: str | None = None,
    ) -> MemoryRecord | None:
        payload = {
            "session_id": session_id,
            "conversation": list(conversation or []),
            "current_task_id": current_task_id,
            "active_context": dict(active_context or {}),
        }
        return self.upsert(
            kind=MemoryKind.SESSION,
            payload=payload,
            record_id=f"session_{session_id}",
            owner_id=owner_id,
        )

    def put_workspace_memory(
        self,
        *,
        workspace_id: str,
        repository: str | None = None,
        branch: str | None = None,
        pr: str | None = None,
        worktree: str | None = None,
        owner_id: str | None = None,
    ) -> MemoryRecord | None:
        payload = {
            "workspace_id": workspace_id,
            "repository": repository,
            "branch": branch,
            "pr": pr,
            "worktree": worktree,
        }
        return self.upsert(
            kind=MemoryKind.WORKSPACE,
            payload=payload,
            record_id=f"workspace_{workspace_id}",
            owner_id=owner_id,
        )

    def put_runtime_memory(
        self,
        *,
        runtime_id: str,
        current_state: str = "Idle",
        safe_mode: bool = False,
        e_stop: bool = False,
        owner_id: str | None = None,
    ) -> MemoryRecord | None:
        payload = {
            "runtime_id": runtime_id,
            "current_state": current_state,
            "safe_mode": bool(safe_mode),
            "e_stop": bool(e_stop),
        }
        return self.upsert(
            kind=MemoryKind.RUNTIME,
            payload=payload,
            record_id=f"runtime_{runtime_id}",
            owner_id=owner_id,
        )

    def create_task(
        self,
        *,
        goal: str,
        owner_id: str | None = None,
        dependencies: Iterable[str] | None = None,
        task_id: str | None = None,
        status: TaskStatus = TaskStatus.PROPOSED,
    ) -> MemoryRecord | None:
        tid = task_id or _new_id("task")
        payload = TaskPayload(
            task_id=tid,
            goal=goal,
            status=status,
            started=utc_now_iso(),
            finished=None,
            dependencies=list(dependencies or []),
            owner_id=owner_id,
            logs=[],
        )
        return self.upsert(
            kind=MemoryKind.TASK,
            payload=payload.to_dict(),
            record_id=f"task_{tid}",
            owner_id=owner_id,
        )

    def append_task_log(self, task_record_id: str, line: str) -> MemoryRecord | None:
        with self._lock:
            if not self._enabled:
                return None
            self._ensure_loaded()
            existing = self._records.get(task_record_id)
            if existing is None or existing.kind != MemoryKind.TASK:
                return None
            tp = TaskPayload.from_dict(existing.payload)
            tp.logs.append(str(line))
            return self.upsert(
                kind=MemoryKind.TASK,
                payload=tp.to_dict(),
                record_id=task_record_id,
                owner_id=existing.owner_id,
            )

    def update_task_status(
        self,
        task_record_id: str,
        status: TaskStatus,
        *,
        finished: bool = False,
    ) -> MemoryRecord | None:
        with self._lock:
            if not self._enabled:
                return None
            self._ensure_loaded()
            existing = self._records.get(task_record_id)
            if existing is None or existing.kind != MemoryKind.TASK:
                return None
            tp = TaskPayload.from_dict(existing.payload)
            tp.status = status
            if finished:
                tp.finished = utc_now_iso()
            return self.upsert(
                kind=MemoryKind.TASK,
                payload=tp.to_dict(),
                record_id=task_record_id,
                owner_id=existing.owner_id,
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            return {
                "enabled": self._enabled,
                "schema": _SCHEMA,
                "revision": self._revision,
                "record_count": len(self._records) if self._enabled else 0,
                "records": {
                    rid: rec.to_dict() for rid, rec in self._records.items()
                }
                if self._enabled
                else {},
            }


_ENGINE: MemoryEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_memory_engine(
    *,
    enabled: bool | None = None,
    path: Path | str | None = None,
) -> MemoryEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = MemoryEngine(enabled=enabled, path=path)
        else:
            if enabled is not None:
                _ENGINE.set_enabled(bool(enabled))
        return _ENGINE


def reset_memory_engine_for_tests() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None
