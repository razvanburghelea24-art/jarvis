"""Versioned data contracts for Brain Memory v2 Preference + Project.

JSON only (no pickle). Unknown fields are ignored; missing fields get
safe defaults. Serialization is deterministic (sorted keys, UTC ISO-8601).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional
import json

PREFERENCE_SCHEMA_VERSION = 1
PROJECT_SCHEMA_VERSION = 1
DOCUMENT_SCHEMA_VERSION = 1

PROJECT_STATUSES = frozenset({"active", "paused", "done", "archived"})

_MAX_KEY_LEN = 128
_MAX_STR = 4000
_MAX_SUMMARY = 8000
_MAX_META_KEYS = 32
_MAX_META_JSON_CHARS = 4000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp_str(value: Any, *, max_len: int = _MAX_STR, default: str = "") -> str:
    if value is None:
        return default
    s = str(value).strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _clamp_confidence(value: Any, default: float = 0.0) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return default
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def _normalize_key(key: Any) -> str:
    """Validate preference / project id keys (no path traversal)."""
    s = _clamp_str(key, max_len=_MAX_KEY_LEN)
    if not s:
        raise ValueError("empty key")
    if s in (".", "..") or "/" in s or "\\" in s or ":" in s:
        raise ValueError("unsafe key")
    # Allow letters, digits, underscore, hyphen, dot only.
    for ch in s:
        if not (ch.isalnum() or ch in "._-"):
            raise ValueError("unsafe key characters")
    return s


def normalize_preference_key(key: Any) -> str:
    return _normalize_key(key)


def normalize_project_id(project_id: Any) -> str:
    return _normalize_key(project_id)


@dataclass
class PreferenceMemoryRecord:
    """A single owner preference candidate or confirmed value."""

    key: str
    value: str
    confidence: float = 0.0
    source: str = "unknown"
    confirmed: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    schema_version: int = PREFERENCE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic JSON-ready mapping (known fields only)."""
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "confirmed": bool(self.confirmed),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": int(self.schema_version),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PreferenceMemoryRecord":
        if not isinstance(raw, Mapping):
            raise ValueError("preference record must be a mapping")
        key = normalize_preference_key(raw.get("key"))
        value = _clamp_str(raw.get("value"), max_len=_MAX_STR)
        conf = _clamp_confidence(raw.get("confidence", 0.0))
        source = _clamp_str(raw.get("source", "unknown"), max_len=120, default="unknown") or "unknown"
        confirmed = bool(raw.get("confirmed", False))
        created = _clamp_str(raw.get("created_at"), max_len=40, default=utc_now_iso()) or utc_now_iso()
        updated = _clamp_str(raw.get("updated_at"), max_len=40, default=created) or created
        try:
            ver = int(raw.get("schema_version", PREFERENCE_SCHEMA_VERSION))
        except (TypeError, ValueError):
            ver = PREFERENCE_SCHEMA_VERSION
        if ver < 1:
            ver = PREFERENCE_SCHEMA_VERSION
        # Unknown keys intentionally ignored (forward-compatible).
        return cls(
            key=key,
            value=value,
            confidence=conf,
            source=source,
            confirmed=confirmed,
            created_at=created,
            updated_at=updated,
            schema_version=ver,
        )


@dataclass
class ProjectMemoryRecord:
    """Tracked project context. Never executes actions — state only."""

    project_id: str
    name: str
    status: str = "active"
    summary: str = ""
    active_goal: str = ""
    last_action: str = ""
    next_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    schema_version: int = PROJECT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        safe_meta: Dict[str, Any] = {}
        for k, v in list(meta.items())[:_MAX_META_KEYS]:
            sk = _clamp_str(k, max_len=64)
            if not sk:
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                safe_meta[sk] = v if not isinstance(v, str) else _clamp_str(v, max_len=500)
            elif isinstance(v, (list, dict)):
                try:
                    encoded = json.dumps(v, ensure_ascii=False, sort_keys=True)
                except (TypeError, ValueError):
                    continue
                if len(encoded) > _MAX_META_JSON_CHARS:
                    continue
                safe_meta[sk] = json.loads(encoded)
        # Drop whole metadata map if still oversized after per-key clamps.
        try:
            meta_blob = json.dumps(safe_meta, ensure_ascii=False, sort_keys=True)
            if len(meta_blob) > _MAX_META_JSON_CHARS:
                safe_meta = {}
        except (TypeError, ValueError):
            safe_meta = {}
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "active_goal": self.active_goal,
            "last_action": self.last_action,
            "next_action": self.next_action,
            "metadata": safe_meta,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": int(self.schema_version),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ProjectMemoryRecord":
        if not isinstance(raw, Mapping):
            raise ValueError("project record must be a mapping")
        pid = normalize_project_id(raw.get("project_id") or raw.get("id"))
        name = _clamp_str(raw.get("name"), max_len=200, default=pid) or pid
        status = _clamp_str(raw.get("status", "active"), max_len=32, default="active").lower() or "active"
        if status not in PROJECT_STATUSES:
            status = "active"
        summary = _clamp_str(raw.get("summary"), max_len=_MAX_SUMMARY)
        active_goal = _clamp_str(raw.get("active_goal"), max_len=_MAX_STR)
        last_action = _clamp_str(raw.get("last_action"), max_len=_MAX_STR)
        next_action = _clamp_str(raw.get("next_action"), max_len=_MAX_STR)
        meta_raw = raw.get("metadata")
        metadata: Dict[str, Any] = dict(meta_raw) if isinstance(meta_raw, dict) else {}
        created = _clamp_str(raw.get("created_at"), max_len=40, default=utc_now_iso()) or utc_now_iso()
        updated = _clamp_str(raw.get("updated_at"), max_len=40, default=created) or created
        try:
            ver = int(raw.get("schema_version", PROJECT_SCHEMA_VERSION))
        except (TypeError, ValueError):
            ver = PROJECT_SCHEMA_VERSION
        if ver < 1:
            ver = PROJECT_SCHEMA_VERSION
        return cls(
            project_id=pid,
            name=name,
            status=status,
            summary=summary,
            active_goal=active_goal,
            last_action=last_action,
            next_action=next_action,
            metadata=metadata,
            created_at=created,
            updated_at=updated,
            schema_version=ver,
        )


def empty_preferences_document() -> Dict[str, Any]:
    return {
        "schema_version": DOCUMENT_SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "items": {},
    }


def empty_projects_document() -> Dict[str, Any]:
    return {
        "schema_version": DOCUMENT_SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "active_project_id": None,
        "items": {},
    }
