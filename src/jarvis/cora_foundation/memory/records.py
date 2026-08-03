"""Versioned memory records — pure data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .kinds import MemoryKind, TaskStatus


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class TaskPayload:
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PROPOSED
    started: str | None = None
    finished: str | None = None
    dependencies: list[str] = field(default_factory=list)
    owner_id: str | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "started": self.started,
            "finished": self.finished,
            "dependencies": list(self.dependencies),
            "owner_id": self.owner_id,
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskPayload":
        status_raw = str(data.get("status") or TaskStatus.PROPOSED.value)
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            status = TaskStatus.PROPOSED
        return cls(
            task_id=str(data.get("task_id") or ""),
            goal=str(data.get("goal") or ""),
            status=status,
            started=data.get("started"),
            finished=data.get("finished"),
            dependencies=[str(x) for x in (data.get("dependencies") or [])],
            owner_id=data.get("owner_id"),
            logs=[str(x) for x in (data.get("logs") or [])],
        )


@dataclass
class MemoryRecord:
    """Envelope for every memory object — unique id + monotonic version."""

    record_id: str
    kind: MemoryKind
    version: int
    created_at: str
    updated_at: str
    payload: dict[str, Any]
    # Optional link to Identity Owner (reference only).
    owner_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "kind": self.kind.value,
            "version": int(self.version),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "payload": dict(self.payload),
            "owner_id": self.owner_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryRecord":
        kind = MemoryKind(str(data.get("kind")))
        return cls(
            record_id=str(data["record_id"]),
            kind=kind,
            version=int(data.get("version") or 1),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            payload=dict(data.get("payload") or {}),
            owner_id=data.get("owner_id"),
        )
