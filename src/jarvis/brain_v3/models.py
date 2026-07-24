"""Validated Brain V3 data contracts (Phase 1)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .errors import ValidationError
from .limits import BrainV3Limits

ENTITY_TYPES = frozenset(
    {
        "person",
        "project",
        "component",
        "decision",
        "goal",
        "task",
        "repository",
        "branch",
        "commit",
        "document",
        "system",
        "feature",
        "environment",
        "event",
        "concept",
    }
)
RELATION_TYPES = frozenset(
    {
        "part_of",
        "depends_on",
        "created_by",
        "owned_by",
        "related_to",
        "decided_in",
        "implemented_by",
        "blocked_by",
        "supersedes",
        "uses",
        "targets",
        "belongs_to",
        "caused_by",
        "verified_by",
    }
)
CONFIDENCE_CATEGORIES = frozenset(
    {
        "verified",
        "user_stated",
        "system_observed",
        "imported",
        "inferred",
        "conflicting",
        "stale",
    }
)
PLAN_STATUSES = frozenset({"draft", "active", "blocked", "done", "archived"})
STEP_STATUSES = frozenset({"pending", "ready", "blocked", "done", "cancelled"})
ENTITY_STATUSES = frozenset({"active", "archived", "superseded", "conflict"})

_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def clamp_confidence(value: Any, limits: BrainV3Limits | None = None) -> float:
    lim = limits or BrainV3Limits()
    try:
        c = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("confidence must be a number") from exc
    if c < lim.min_confidence or c > lim.max_confidence:
        raise ValidationError("confidence out of bounds")
    return c


def clamp_str(value: Any, *, max_len: int, required: bool = False, field: str = "value") -> str:
    if value is None:
        if required:
            raise ValidationError(f"{field} required")
        return ""
    s = str(value).strip()
    if required and not s:
        raise ValidationError(f"{field} required")
    if len(s) > max_len:
        s = s[:max_len]
    return s


def normalize_key(name: str, *, max_len: int = 256) -> str:
    s = clamp_str(name, max_len=max_len, required=True, field="name").lower()
    return re.sub(r"\s+", " ", s)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_id(value: Any, *, field: str = "id") -> str:
    s = clamp_str(value, max_len=128, required=True, field=field)
    if not _ID_RE.match(s):
        raise ValidationError(f"invalid {field}")
    return s


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class SourceRecord:
    id: str
    source_type: str
    source_reference: str
    content_hash: str
    captured_at: str
    trust_level: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "content_hash": self.content_hash,
            "captured_at": self.captured_at,
            "trust_level": self.trust_level,
            "metadata": self.metadata,
        }


@dataclass
class Entity:
    id: str
    entity_type: str
    canonical_name: str
    display_name: str
    description: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    source_id: Optional[str] = None
    confidence: float = 0.5
    confidence_category: str = "user_stated"
    status: str = "active"
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "description": self.description,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "confidence_category": self.confidence_category,
            "status": self.status,
            "aliases": list(self.aliases),
        }


@dataclass
class Relation:
    id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    confidence: float = 0.5
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_entity_id": self.source_entity_id,
            "relation_type": self.relation_type,
            "target_entity_id": self.target_entity_id,
            "attributes": self.attributes,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
        }


@dataclass
class TimelineEvent:
    id: str
    event_type: str
    title: str
    description: str = ""
    occurred_at: str = field(default_factory=utc_now_iso)
    recorded_at: str = field(default_factory=utc_now_iso)
    entity_ids: List[str] = field(default_factory=list)
    source_id: Optional[str] = None
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "occurred_at": self.occurred_at,
            "recorded_at": self.recorded_at,
            "entity_ids": list(self.entity_ids),
            "source_id": self.source_id,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class PlanStep:
    id: str
    plan_id: str
    order_index: int
    title: str
    description: str = ""
    status: str = "pending"
    dependencies: List[str] = field(default_factory=list)
    risk_level: str = "low"
    requires_approval: bool = True
    execution_forbidden: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "order_index": self.order_index,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "risk_level": self.risk_level,
            "requires_approval": True,
            "execution_forbidden": True,
        }


@dataclass
class Plan:
    id: str
    goal_entity_id: Optional[str]
    title: str
    status: str = "draft"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    source_id: Optional[str] = None
    confidence: float = 0.5
    assumptions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    approval_points: List[str] = field(default_factory=list)
    verification_steps: List[str] = field(default_factory=list)
    rollback_notes: List[str] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal_entity_id": self.goal_entity_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "assumptions": list(self.assumptions),
            "constraints": list(self.constraints),
            "risks": list(self.risks),
            "approval_points": list(self.approval_points),
            "verification_steps": list(self.verification_steps),
            "rollback_notes": list(self.rollback_notes),
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ConflictRecord:
    id: str
    entity_id: str
    field: str
    value_a: str
    value_b: str
    source_a: Optional[str]
    source_b: Optional[str]
    created_at: str = field(default_factory=utc_now_iso)
    status: str = "open"
    requires_confirmation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "field": self.field,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "created_at": self.created_at,
            "status": self.status,
            "requires_confirmation": True,
        }
