"""Bounded contextual retrieval via BrainV3Service (no direct SQLite)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .contradictions import detect_item_contradictions
from .filters import (
    entity_allowed_for_recall,
    filter_excluded_record,
    redact_for_output,
)
from .limits import RecallLimits
from .models import ContextBundle, RecallItem, RecallRequest
from .provenance import build_provenance
from .ranking import rank_items
from .temporal import in_time_range, temporal_state_for
from .explanations import summarize_selection

if TYPE_CHECKING:
    from ..service import BrainV3Service


def _entity_to_item(entity: Any) -> RecallItem:
    attrs = dict(getattr(entity, "attributes", {}) or {})
    text = redact_for_output(
        f"{getattr(entity, 'display_name', '')}: {getattr(entity, 'description', '')}"
    )
    temporal = temporal_state_for(
        status=str(getattr(entity, "status", "active")),
        valid_from=attrs.get("valid_from"),
        valid_until=attrs.get("valid_until"),
        occurred_at=attrs.get("occurred_at"),
        observed_at=attrs.get("observed_at"),
        recorded_at=attrs.get("recorded_at") or getattr(entity, "updated_at", None),
        superseded=str(getattr(entity, "status", "")) == "superseded",
    )
    category = str(getattr(entity, "confidence_category", "") or "")
    item_type = "preference" if getattr(entity, "entity_type", "") == "concept" and "preference" in category else "entity"
    if getattr(entity, "entity_type", "") == "decision":
        item_type = "decision"
    elif getattr(entity, "entity_type", "") == "goal":
        item_type = "goal"
    elif attrs.get("is_preference"):
        item_type = "preference"
    return RecallItem(
        item_id=str(entity.id),
        item_type=item_type,
        title=redact_for_output(str(getattr(entity, "display_name", "") or entity.id)),
        content=text,
        source_ids=[str(getattr(entity, "source_id", "") or "")] if getattr(entity, "source_id", None) else [],
        entity_ids=[str(entity.id)],
        confidence=float(getattr(entity, "confidence", 0.0) or 0.0),
        approval_state=str(attrs.get("approval_state") or "committed"),
        temporal_state=temporal,
        sensitivity="normal",
        provenance=build_provenance(
            source_type="brain_v3_entity",
            source_reference=str(getattr(entity, "source_id", "") or ""),
            source_id=str(getattr(entity, "source_id", "") or ""),
            approval_state=str(attrs.get("approval_state") or "committed"),
            confidence=float(getattr(entity, "confidence", 0.0) or 0.0),
            confidence_category=category,
            temporal_state=temporal,
        ),
        metadata={
            "confidence_category": category,
            "entity_type": getattr(entity, "entity_type", ""),
            "canonical_name": getattr(entity, "canonical_name", ""),
            "created_at": getattr(entity, "created_at", ""),
            "updated_at": getattr(entity, "updated_at", ""),
            "valid_from": attrs.get("valid_from"),
            "valid_until": attrs.get("valid_until"),
            "occurred_at": attrs.get("occurred_at"),
            "recorded_at": attrs.get("recorded_at"),
            **{k: attrs[k] for k in ("is_preference", "head", "branch", "phase") if k in attrs},
        },
    )


def retrieve_approved_context(
    brain: "BrainV3Service",
    request: RecallRequest,
    *,
    limits: Optional[RecallLimits] = None,
    include_sensitive: bool = False,
) -> ContextBundle:
    """Read-only recall over committed Brain V3 graph data via service API."""
    lim = limits or RecallLimits()
    started = time.perf_counter()
    timeout_s = max(1, lim.timeout_ms) / 1000.0
    excluded: List[Dict[str, Any]] = []
    items: List[RecallItem] = []
    truncated = False
    limit_hit = ""

    # Use existing Phase 1 retrieve_context through the service facade.
    base = brain.retrieve_context(
        request.query,
        project_id=request.project_scope or None,
        min_confidence=max(request.minimum_confidence, lim.min_confidence),
        max_results=min(request.maximum_results, lim.max_items),
    )

    entities = list(base.get("entities") or [])
    for entity in entities:
        if time.perf_counter() - started > timeout_s:
            truncated = True
            limit_hit = "timeout_ms"
            break
        ok, reason = entity_allowed_for_recall(
            entity,
            approved_only=request.approved_only,
            include_inferences=request.include_inferences,
            include_sensitive=include_sensitive,
            min_confidence=request.minimum_confidence,
        )
        if not ok:
            excluded.append(
                filter_excluded_record(
                    item_id=str(entity.id),
                    item_type="entity",
                    reason=reason,
                    title=str(getattr(entity, "display_name", "")),
                )
            )
            continue
        if request.entity_scope and entity.id not in request.entity_scope:
            excluded.append(
                filter_excluded_record(
                    item_id=str(entity.id),
                    item_type="entity",
                    reason="outside_entity_scope",
                    title=str(getattr(entity, "display_name", "")),
                )
            )
            continue
        stamp = getattr(entity, "updated_at", None) or getattr(entity, "created_at", None)
        if not in_time_range(stamp, request.time_range):
            excluded.append(
                filter_excluded_record(
                    item_id=str(entity.id),
                    item_type="entity",
                    reason="outside_time_range",
                    title=str(getattr(entity, "display_name", "")),
                )
            )
            continue
        if not request.include_preferences and (
            (getattr(entity, "attributes", {}) or {}).get("is_preference")
            or getattr(entity, "entity_type", "") == "concept"
            and "prefer" in (getattr(entity, "display_name", "") or "").lower()
        ):
            # soft skip preferences when disabled
            attrs = getattr(entity, "attributes", {}) or {}
            if attrs.get("is_preference"):
                excluded.append(
                    filter_excluded_record(
                        item_id=str(entity.id),
                        item_type="preference",
                        reason="preferences_disabled",
                        title=str(getattr(entity, "display_name", "")),
                    )
                )
                continue
        if not request.include_decisions and getattr(entity, "entity_type", "") == "decision":
            excluded.append(
                filter_excluded_record(
                    item_id=str(entity.id),
                    item_type="decision",
                    reason="decisions_disabled",
                    title=str(getattr(entity, "display_name", "")),
                )
            )
            continue
        items.append(_entity_to_item(entity))
        if len(items) >= lim.max_entities:
            truncated = True
            limit_hit = "max_entities"
            break

    relations_out: List[Dict[str, Any]] = []
    if request.include_relations:
        for rel in list(base.get("relations") or [])[: lim.max_relations]:
            relations_out.append(
                {
                    "id": rel.id,
                    "relation_type": rel.relation_type,
                    "source_entity_id": rel.source_entity_id,
                    "target_entity_id": rel.target_entity_id,
                    "status": rel.status,
                }
            )
        if len(list(base.get("relations") or [])) > lim.max_relations:
            truncated = True
            limit_hit = limit_hit or "max_relations"

    timeline_out: List[Dict[str, Any]] = []
    if request.include_timeline:
        for ev in list(base.get("timeline_events") or [])[: lim.max_timeline_events]:
            timeline_out.append(
                {
                    "id": ev.id,
                    "event_type": ev.event_type,
                    "title": redact_for_output(ev.title),
                    "description": redact_for_output(ev.description),
                    "occurred_at": getattr(ev, "occurred_at", ""),
                }
            )
            items.append(
                RecallItem(
                    item_id=str(ev.id),
                    item_type="timeline_event",
                    title=redact_for_output(ev.title),
                    content=redact_for_output(ev.description or ev.title),
                    timeline_event_ids=[str(ev.id)],
                    entity_ids=list(getattr(ev, "entity_ids", []) or []),
                    confidence=float(getattr(ev, "confidence", 0.8) or 0.8),
                    approval_state="committed",
                    temporal_state=temporal_state_for(
                        occurred_at=getattr(ev, "occurred_at", None),
                        recorded_at=getattr(ev, "created_at", None),
                    ),
                    reason_for_selection="timeline_match",
                    provenance=build_provenance(
                        source_type="timeline_event",
                        source_reference=str(getattr(ev, "source_id", "") or ""),
                        temporal_state="historical",
                        confidence=float(getattr(ev, "confidence", 0.8) or 0.8),
                    ),
                    metadata={
                        "occurred_at": getattr(ev, "occurred_at", ""),
                        "created_at": getattr(ev, "created_at", ""),
                        "confidence_category": "system_observed",
                    },
                )
            )
        if len(list(base.get("timeline_events") or [])) > lim.max_timeline_events:
            truncated = True
            limit_hit = limit_hit or "max_timeline_events"

    sources_out: List[Dict[str, Any]] = []
    for src in list(base.get("sources") or [])[: lim.max_sources]:
        sources_out.append(
            {
                "id": src.id,
                "source_type": src.source_type,
                "reference": redact_for_output(str(getattr(src, "reference", "") or "")),
            }
        )

    items, contradictions = detect_item_contradictions(items)
    items = rank_items(
        items,
        query=request.query,
        project_scope=request.project_scope,
        entity_scope=request.entity_scope,
    )
    max_results = lim.clamp_results(request.maximum_results)
    if len(items) > max_results:
        for dropped in items[max_results:]:
            excluded.append(
                filter_excluded_record(
                    item_id=dropped.item_id,
                    item_type=dropped.item_type,
                    reason="max_results",
                    title=dropped.title,
                )
            )
        items = items[:max_results]
        truncated = True
        limit_hit = limit_hit or "max_results"

    # character budget
    used = 0
    kept: List[RecallItem] = []
    for item in items:
        cost = len(item.title) + len(item.content)
        if used + cost > lim.max_characters:
            truncated = True
            limit_hit = limit_hit or "max_characters"
            excluded.append(
                filter_excluded_record(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    reason="max_characters",
                    title=item.title,
                )
            )
            continue
        used += cost
        kept.append(item)
    items = kept

    # rough token budget (~4 chars/token)
    token_budget = lim.max_tokens * 4
    used = 0
    final_items: List[RecallItem] = []
    for item in items:
        cost = len(item.title) + len(item.content)
        if used + cost > token_budget:
            truncated = True
            limit_hit = limit_hit or "max_tokens"
            excluded.append(
                filter_excluded_record(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    reason="max_tokens",
                    title=item.title,
                )
            )
            continue
        used += cost
        final_items.append(item)

    explanation = summarize_selection(final_items, excluded, truncated)
    if limit_hit:
        explanation = f"{explanation}; limit={limit_hit}"

    return ContextBundle(
        request_id=request.request_id,
        query=request.query,
        items=final_items,
        entities=[
            {
                "id": e.id,
                "display_name": redact_for_output(e.display_name),
                "entity_type": e.entity_type,
                "confidence": e.confidence,
                "confidence_category": e.confidence_category,
            }
            for e in entities
            if any(i.item_id == e.id for i in final_items)
        ],
        relations=relations_out,
        timeline_events=timeline_out,
        sources=sources_out,
        contradictions=contradictions,
        unknowns=[],
        excluded_items=excluded,
        selection_explanation=explanation,
        limits_applied={
            "max_items": lim.max_items,
            "max_entities": lim.max_entities,
            "max_relations": lim.max_relations,
            "max_timeline_events": lim.max_timeline_events,
            "max_sources": lim.max_sources,
            "max_characters": lim.max_characters,
            "max_tokens": lim.max_tokens,
            "timeout_ms": lim.timeout_ms,
            "limit_hit": limit_hit or None,
        },
        truncated=truncated,
    )
