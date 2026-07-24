"""Project Memory — active project state (Brain Memory v2). Never executes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .models import (
    PROJECT_STATUSES,
    ProjectMemoryRecord,
    empty_projects_document,
    normalize_project_id,
    utc_now_iso,
)
from .persistence import BrainV2JsonStore
from .types import MemoryKind, MemoryRecord, MemoryScope, MemoryStatus

__all__ = ["ProjectMemory", "ProjectMemoryStub"]


class ProjectMemory:
    """Project context store. Reading/updating state never runs actions."""

    kind = MemoryKind.PROJECT

    def __init__(self, store: Optional[BrainV2JsonStore] = None) -> None:
        self._store = store or BrainV2JsonStore(
            path="projects.json",
            empty_factory=empty_projects_document,
            writable=False,
        )

    def create(
        self,
        project_id: str,
        name: str,
        *,
        summary: str = "",
        active_goal: str = "",
        next_action: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "active",
    ) -> Optional[ProjectMemoryRecord]:
        try:
            pid = normalize_project_id(project_id)
        except ValueError:
            return None
        if self.get(pid) is not None:
            return None
        now = utc_now_iso()
        st = (status or "active").lower()
        if st not in PROJECT_STATUSES or st == "archived":
            st = "active"
        rec = ProjectMemoryRecord.from_dict(
            {
                "project_id": pid,
                "name": name or pid,
                "status": st,
                "summary": summary,
                "active_goal": active_goal,
                "last_action": "",
                "next_action": next_action,
                "metadata": metadata or {},
                "created_at": now,
                "updated_at": now,
            }
        )

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items[pid] = rec.to_dict()
            doc["updated_at"] = now
            doc.setdefault("schema_version", 1)
            if doc.get("active_project_id") is None:
                doc["active_project_id"] = pid

        if not self._store.mutate(_mut):
            return None
        return rec

    def get(self, project_id: str) -> Optional[ProjectMemoryRecord]:
        try:
            pid = normalize_project_id(project_id)
        except ValueError:
            return None
        items = self._store.snapshot().get("items") or {}
        raw = items.get(pid)
        if not isinstance(raw, dict):
            return None
        try:
            return ProjectMemoryRecord.from_dict(raw)
        except ValueError:
            return None

    def list(self) -> Sequence[ProjectMemoryRecord]:
        items = self._store.snapshot().get("items") or {}
        out: List[ProjectMemoryRecord] = []
        for raw in items.values():
            if not isinstance(raw, dict):
                continue
            try:
                out.append(ProjectMemoryRecord.from_dict(raw))
            except ValueError:
                continue
        out.sort(key=lambda r: r.project_id)
        return out

    def set_active(self, project_id: str) -> bool:
        try:
            pid = normalize_project_id(project_id)
        except ValueError:
            return False
        rec = self.get(pid)
        if rec is None or rec.status == "archived":
            return False
        now = utc_now_iso()

        def _mut(doc: Dict[str, Any]) -> None:
            doc["active_project_id"] = pid
            doc["updated_at"] = now

        return self._store.mutate(_mut)

    def get_active(self) -> Optional[str]:
        aid = self._store.snapshot().get("active_project_id")
        if aid is None:
            return None
        try:
            pid = normalize_project_id(aid)
        except ValueError:
            return None
        rec = self.get(pid)
        if rec is None or rec.status == "archived":
            return None
        return pid

    def update_status(self, project_id: str, status: str) -> Optional[ProjectMemoryRecord]:
        try:
            pid = normalize_project_id(project_id)
        except ValueError:
            return None
        st = (status or "").lower().strip()
        if st not in PROJECT_STATUSES:
            return None
        existing = self.get(pid)
        if existing is None:
            return None
        now = utc_now_iso()
        updated = ProjectMemoryRecord.from_dict({**existing.to_dict(), "status": st, "updated_at": now})

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items[pid] = updated.to_dict()
            doc["updated_at"] = now
            if st == "archived" and doc.get("active_project_id") == pid:
                doc["active_project_id"] = None

        if not self._store.mutate(_mut):
            return None
        return updated

    def update_next_action(
        self,
        project_id: str,
        next_action: str,
        *,
        last_action: Optional[str] = None,
    ) -> Optional[ProjectMemoryRecord]:
        try:
            pid = normalize_project_id(project_id)
        except ValueError:
            return None
        existing = self.get(pid)
        if existing is None or existing.status == "archived":
            return None
        now = utc_now_iso()
        payload = {
            **existing.to_dict(),
            "next_action": next_action,
            "updated_at": now,
        }
        if last_action is not None:
            payload["last_action"] = last_action
        updated = ProjectMemoryRecord.from_dict(payload)

        def _mut(doc: Dict[str, Any]) -> None:
            items = doc.setdefault("items", {})
            items[pid] = updated.to_dict()
            doc["updated_at"] = now

        if not self._store.mutate(_mut):
            return None
        return updated

    def archive(self, project_id: str) -> bool:
        return self.update_status(project_id, "archived") is not None

    def clear(self) -> None:
        self._store.replace(empty_projects_document())

    # --- Protocol bridge ----------------------------------------------------

    def put(self, record: MemoryRecord) -> MemoryRecord:
        if record.kind != MemoryKind.PROJECT:
            raise ValueError("project store rejected non-project record")
        pid = record.project_id or record.record_id
        if self.get(str(pid)) is None:
            created = self.create(str(pid), record.content or str(pid), summary=record.content)
            if created is None:
                raise RuntimeError("project create failed")
        return record

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        status: Optional[MemoryStatus] = None,
    ) -> Sequence[MemoryRecord]:
        q = (query or "").strip().lower()
        out: List[MemoryRecord] = []
        for proj in self.list():
            if status is not None and proj.status == "archived" and status != MemoryStatus.FORGOTTEN:
                continue
            blob = f"{proj.project_id} {proj.name} {proj.summary}".lower()
            if q and q not in blob:
                continue
            out.append(
                MemoryRecord(
                    kind=MemoryKind.PROJECT,
                    content=proj.summary or proj.name,
                    record_id=proj.project_id,
                    status=MemoryStatus.ACTIVE,
                    scope=MemoryScope.PROJECT,
                    project_id=proj.project_id,
                    payload={"status": proj.status, "next_action": proj.next_action},
                )
            )
            if len(out) >= max(1, int(limit)):
                break
        return out

    def forget(self, record_id: str) -> bool:
        return self.archive(record_id)

    def set_active_project(self, project_id: str) -> None:
        self.set_active(project_id)

    def get_active_project(self) -> Optional[str]:
        return self.get_active()


ProjectMemoryStub = ProjectMemory
