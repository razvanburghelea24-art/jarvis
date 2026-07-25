"""Request validation for Phase 3 conversational intelligence."""

from __future__ import annotations

from typing import Any, Mapping

from ..errors import ValidationError
from ..recall.models import RecallRequest


def parse_recall_request(raw: Mapping[str, Any] | RecallRequest) -> RecallRequest:
    if isinstance(raw, RecallRequest):
        return raw
    if not isinstance(raw, Mapping):
        raise ValidationError("recall request must be a mapping")
    return RecallRequest(
        request_id=str(raw.get("request_id") or ""),
        query=str(raw.get("query") or ""),
        conversation_id=str(raw.get("conversation_id") or ""),
        project_scope=str(raw.get("project_scope") or ""),
        entity_scope=list(raw.get("entity_scope") or []),
        time_range=raw.get("time_range"),
        minimum_confidence=float(raw.get("minimum_confidence") or 0.0),
        maximum_results=int(raw.get("maximum_results") or 32),
        include_timeline=bool(raw.get("include_timeline", True)),
        include_relations=bool(raw.get("include_relations", True)),
        include_preferences=bool(raw.get("include_preferences", True)),
        include_decisions=bool(raw.get("include_decisions", True)),
        include_inferences=bool(raw.get("include_inferences", False)),
        approved_only=bool(raw.get("approved_only", True)),
        metadata=dict(raw.get("metadata") or {}),
    )
