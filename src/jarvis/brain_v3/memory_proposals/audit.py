"""Append-only audit log for Phase 2 memory proposal actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from ..models import utc_now_iso

_PathLike = Union[str, Path]


class ProposalAuditLog:
    """In-memory audit buffer with optional JSONL persistence."""

    def __init__(self, root_dir: Optional[_PathLike] = None) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._root_dir: Optional[Path] = None
        self._audit_path: Optional[Path] = None
        if root_dir is not None:
            self._root_dir = Path(root_dir).expanduser().resolve()
            phase2_dir = self._root_dir / "phase2"
            phase2_dir.mkdir(parents=True, exist_ok=True)
            self._audit_path = phase2_dir / "phase2_audit.jsonl"

    @property
    def path(self) -> Optional[Path]:
        return self._audit_path

    def append(self, event_type: str, data: Mapping[str, Any]) -> Dict[str, Any]:
        entry = {
            "timestamp": utc_now_iso(),
            "event_type": event_type,
            "data": dict(data),
        }
        self._entries.append(entry)
        if self._audit_path is not None:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        return entry

    def entries(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def load_from_disk(self) -> List[Dict[str, Any]]:
        if self._audit_path is None or not self._audit_path.exists():
            return []
        loaded: List[Dict[str, Any]] = []
        with self._audit_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                loaded.append(json.loads(line))
        self._entries.extend(loaded)
        return loaded
