"""Phase 3 recall data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import ValidationError
from ..models import new_id, utc_now_iso

ITEM_TYPES = frozenset(
    {
        "entity",
        "relation",
        "timeline_event",
        "preference",
        "decision",
        "goal",
        "source",
        "contradiction",
    }
)
APPROVAL_STATES = frozenset(
    {
        "committed",
        "draft",
        "rejected",
        "expired",
        "rolled_back",
        "unknown",
        "blocked_sensitive",
    }
)
TEMPORAL_STATES = frozenset(
    {
        "current",
        "historical",
        "superseded",
        "stale",
        "unspecified",
        "valid_interval",
    }
)
CONTRADICTION_STATES = frozenset(
    {
        "none",
        "resolved",
        "unresolved",
        "historical_transition",
        "needs_review",
    }
)
SENSITIVITY_LEVELS = frozenset({"normal", "sensitive", "blocked", "authority_related"})


@dataclass
class RecallRequest:
    request_id: str = ""
    query: str = ""
    conversation_id: str = ""
    project_scope: str = ""
    entity_scope: List[str] = field(default_factory=list)
    time_range: Optional[Dict[str, str]] = None
    minimum_confidence: float = 0.0
    maximum_results: int = 32
    include_timeline: bool = True
    include_relations: bool = True
    include_preferences: bool = True
    include_decisions: bool = True
    include_inferences: bool = False
    approved_only: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = new_id("recall")
        self.query = str(self.query or "")
        self.minimum_confidence = max(0.0, min(1.0, float(self.minimum_confidence)))
        self.maximum_results = max(1, int(self.maximum_results))
        self.approved_only = bool(self.approved_only)
        self.include_inferences = bool(self.include_inferences)
        if self.time_range is not None and not isinstance(self.time_range, dict):
            raise ValidationError("time_range must be a dict or None")
        if not isinstance(self.entity_scope, list):
            raise ValidationError("entity_scope must be a list")
        if not isinstance(self.metadata, dict):
            raise ValidationError("metadata must be a dict")


@dataclass
class RecallItem:
    item_id: str
    item_type: str
    title: str
    content: str
    source_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    relation_ids: List[str] = field(default_factory=list)
    timeline_event_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    approval_state: str = "committed"
    temporal_state: str = "unspecified"
    contradiction_state: str = "none"
    sensitivity: str = "normal"
    reason_for_selection: str = ""
    rank_score: float = 0.0
    rank_breakdown: Dict[str, float] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.item_type not in ITEM_TYPES:
            raise ValidationError(f"invalid item_type: {self.item_type}")
        if self.approval_state not in APPROVAL_STATES:
            raise ValidationError(f"invalid approval_state: {self.approval_state}")
        if self.temporal_state not in TEMPORAL_STATES:
            raise ValidationError(f"invalid temporal_state: {self.temporal_state}")
        if self.contradiction_state not in CONTRADICTION_STATES:
            raise ValidationError(f"invalid contradiction_state: {self.contradiction_state}")
        if self.sensitivity not in SENSITIVITY_LEVELS:
            raise ValidationError(f"invalid sensitivity: {self.sensitivity}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.rank_score = float(self.rank_score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "title": self.title,
            "content": self.content,
            "source_ids": list(self.source_ids),
            "entity_ids": list(self.entity_ids),
            "relation_ids": list(self.relation_ids),
            "timeline_event_ids": list(self.timeline_event_ids),
            "confidence": self.confidence,
            "approval_state": self.approval_state,
            "temporal_state": self.temporal_state,
            "contradiction_state": self.contradiction_state,
            "sensitivity": self.sensitivity,
            "reason_for_selection": self.reason_for_selection,
            "rank_score": self.rank_score,
            "rank_breakdown": dict(self.rank_breakdown),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }


@dataclass
class ContextBundle:
    request_id: str
    query: str
    items: List[RecallItem] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    excluded_items: List[Dict[str, Any]] = field(default_factory=list)
    selection_explanation: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    limits_applied: Dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    execution_forbidden: bool = True

    def __post_init__(self) -> None:
        self.execution_forbidden = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "query": self.query,
            "items": [i.to_dict() for i in self.items],
            "entities": list(self.entities),
            "relations": list(self.relations),
            "timeline_events": list(self.timeline_events),
            "sources": list(self.sources),
            "contradictions": list(self.contradictions),
            "unknowns": list(self.unknowns),
            "excluded_items": list(self.excluded_items),
            "selection_explanation": self.selection_explanation,
            "generated_at": self.generated_at,
            "limits_applied": dict(self.limits_applied),
            "truncated": self.truncated,
            "execution_forbidden": True,
        }
