"""Dict-to-model validation helpers for Brain V3 Phase 1."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .confidence import categorize_confidence
from .errors import ValidationError
from .limits import BrainV3Limits
from .models import (
    ENTITY_STATUSES,
    ENTITY_TYPES,
    PLAN_STATUSES,
    RELATION_TYPES,
    STEP_STATUSES,
    Entity,
    Plan,
    PlanStep,
    Relation,
    SourceRecord,
    TimelineEvent,
    clamp_confidence,
    clamp_str,
    ensure_id,
    new_id,
    normalize_key,
    utc_now_iso,
)


def _require_dict(value: Any, *, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a dict")
    return value


def _optional_dict(value: Any, *, field: str) -> Dict[str, Any]:
    if value is None:
        return {}
    return _require_dict(value, field=field)


def _string_list(value: Any, *, field: str, max_items: int, max_len: int) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    out: List[str] = []
    for item in value[:max_items]:
        out.append(clamp_str(item, max_len=max_len, required=True, field=field))
    return out


def _enum(value: Any, *, allowed: frozenset[str], field: str) -> str:
    s = clamp_str(value, max_len=64, required=True, field=field)
    if s not in allowed:
        raise ValidationError(f"invalid {field}")
    return s


def build_source_record(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> SourceRecord:
    lim = limits or BrainV3Limits()
    d = dict(data)
    source_id = ensure_id(d.get("id") or new_id("src"), field="id")
    source_type = clamp_str(
        d.get("source_type"),
        max_len=lim.max_name_len,
        required=True,
        field="source_type",
    )
    source_reference = clamp_str(
        d.get("source_reference"),
        max_len=lim.max_text_len,
        required=True,
        field="source_reference",
    )
    content_hash = clamp_str(
        d.get("content_hash"),
        max_len=128,
        required=True,
        field="content_hash",
    )
    captured_at = clamp_str(d.get("captured_at") or utc_now_iso(), max_len=64, required=True, field="captured_at")
    trust_level = clamp_confidence(d.get("trust_level", 0.5), lim)
    metadata = _optional_dict(d.get("metadata"), field="metadata")
    return SourceRecord(
        id=source_id,
        source_type=source_type,
        source_reference=source_reference,
        content_hash=content_hash,
        captured_at=captured_at,
        trust_level=trust_level,
        metadata=metadata,
    )


def build_entity(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> Entity:
    lim = limits or BrainV3Limits()
    d = dict(data)
    entity_type = _enum(d.get("entity_type"), allowed=ENTITY_TYPES, field="entity_type")
    canonical_name = normalize_key(
        clamp_str(d.get("canonical_name"), max_len=lim.max_name_len, required=True, field="canonical_name"),
        max_len=lim.max_name_len,
    )
    display_name = clamp_str(
        d.get("display_name") or canonical_name,
        max_len=lim.max_name_len,
        required=True,
        field="display_name",
    )
    description = clamp_str(d.get("description"), max_len=lim.max_text_len, field="description")
    attributes = _optional_dict(d.get("attributes"), field="attributes")
    confidence = clamp_confidence(d.get("confidence", 0.5), lim)
    confidence_category = categorize_confidence(d.get("confidence_category", "user_stated"))
    status = _enum(d.get("status", "active"), allowed=ENTITY_STATUSES, field="status")
    aliases = _string_list(
        d.get("aliases"),
        field="aliases",
        max_items=lim.max_batch_size,
        max_len=lim.max_name_len,
    )
    source_id_raw = d.get("source_id")
    source_id = ensure_id(source_id_raw, field="source_id") if source_id_raw else None
    return Entity(
        id=ensure_id(d.get("id") or new_id("ent"), field="id"),
        entity_type=entity_type,
        canonical_name=canonical_name,
        display_name=display_name,
        description=description,
        attributes=attributes,
        created_at=clamp_str(d.get("created_at") or utc_now_iso(), max_len=64, required=True, field="created_at"),
        updated_at=clamp_str(d.get("updated_at") or utc_now_iso(), max_len=64, required=True, field="updated_at"),
        source_id=source_id,
        confidence=confidence,
        confidence_category=confidence_category,
        status=status,
        aliases=aliases,
    )


def build_relation(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> Relation:
    lim = limits or BrainV3Limits()
    d = dict(data)
    relation_type = _enum(d.get("relation_type"), allowed=RELATION_TYPES, field="relation_type")
    source_entity_id = ensure_id(d.get("source_entity_id"), field="source_entity_id")
    target_entity_id = ensure_id(d.get("target_entity_id"), field="target_entity_id")
    if source_entity_id == target_entity_id:
        raise ValidationError("relation cannot be self-referential")
    attributes = _optional_dict(d.get("attributes"), field="attributes")
    confidence = clamp_confidence(d.get("confidence", 0.5), lim)
    status = _enum(d.get("status", "active"), allowed=ENTITY_STATUSES, field="status")
    source_id_raw = d.get("source_id")
    source_id = ensure_id(source_id_raw, field="source_id") if source_id_raw else None
    return Relation(
        id=ensure_id(d.get("id") or new_id("rel"), field="id"),
        source_entity_id=source_entity_id,
        relation_type=relation_type,
        target_entity_id=target_entity_id,
        attributes=attributes,
        source_id=source_id,
        confidence=confidence,
        created_at=clamp_str(d.get("created_at") or utc_now_iso(), max_len=64, required=True, field="created_at"),
        updated_at=clamp_str(d.get("updated_at") or utc_now_iso(), max_len=64, required=True, field="updated_at"),
        status=status,
    )


def build_timeline_event(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> TimelineEvent:
    lim = limits or BrainV3Limits()
    d = dict(data)
    event_type = clamp_str(d.get("event_type"), max_len=lim.max_name_len, required=True, field="event_type")
    title = clamp_str(d.get("title"), max_len=lim.max_name_len, required=True, field="title")
    description = clamp_str(d.get("description"), max_len=lim.max_text_len, field="description")
    occurred_at = clamp_str(d.get("occurred_at") or utc_now_iso(), max_len=64, required=True, field="occurred_at")
    recorded_at = clamp_str(d.get("recorded_at") or utc_now_iso(), max_len=64, required=True, field="recorded_at")
    entity_ids = [
        ensure_id(item, field="entity_id")
        for item in _string_list(
            d.get("entity_ids"),
            field="entity_ids",
            max_items=lim.max_batch_size,
            max_len=128,
        )
    ]
    metadata = _optional_dict(d.get("metadata"), field="metadata")
    confidence = clamp_confidence(d.get("confidence", 0.5), lim)
    source_id_raw = d.get("source_id")
    source_id = ensure_id(source_id_raw, field="source_id") if source_id_raw else None
    return TimelineEvent(
        id=ensure_id(d.get("id") or new_id("evt"), field="id"),
        event_type=event_type,
        title=title,
        description=description,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        entity_ids=entity_ids,
        source_id=source_id,
        confidence=confidence,
        metadata=metadata,
    )


def build_plan_step(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> PlanStep:
    lim = limits or BrainV3Limits()
    d = dict(data)
    plan_id = ensure_id(d.get("plan_id"), field="plan_id")
    title = clamp_str(d.get("title"), max_len=lim.max_name_len, required=True, field="title")
    description = clamp_str(d.get("description"), max_len=lim.max_text_len, field="description")
    status = _enum(d.get("status", "pending"), allowed=STEP_STATUSES, field="status")
    dependencies = [
        ensure_id(item, field="dependency")
        for item in _string_list(
            d.get("dependencies"),
            field="dependencies",
            max_items=lim.max_plan_steps,
            max_len=128,
        )
    ]
    risk_level = clamp_str(d.get("risk_level", "low"), max_len=32, required=True, field="risk_level")
    try:
        order_index = int(d.get("order_index", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("order_index must be an integer") from exc
    return PlanStep(
        id=ensure_id(d.get("id") or new_id("step"), field="id"),
        plan_id=plan_id,
        order_index=order_index,
        title=title,
        description=description,
        status=status,
        dependencies=dependencies,
        risk_level=risk_level,
        requires_approval=True,
        execution_forbidden=True,
    )


def build_plan(data: Mapping[str, Any], limits: BrainV3Limits | None = None) -> Plan:
    lim = limits or BrainV3Limits()
    d = dict(data)
    title = clamp_str(d.get("title"), max_len=lim.max_name_len, required=True, field="title")
    status = _enum(d.get("status", "draft"), allowed=PLAN_STATUSES, field="status")
    confidence = clamp_confidence(d.get("confidence", 0.5), lim)
    goal_raw = d.get("goal_entity_id")
    goal_entity_id = ensure_id(goal_raw, field="goal_entity_id") if goal_raw else None
    source_id_raw = d.get("source_id")
    source_id = ensure_id(source_id_raw, field="source_id") if source_id_raw else None
    assumptions = _string_list(
        d.get("assumptions"),
        field="assumptions",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    constraints = _string_list(
        d.get("constraints"),
        field="constraints",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    risks = _string_list(
        d.get("risks"),
        field="risks",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    approval_points = _string_list(
        d.get("approval_points"),
        field="approval_points",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    verification_steps = _string_list(
        d.get("verification_steps"),
        field="verification_steps",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    rollback_notes = _string_list(
        d.get("rollback_notes"),
        field="rollback_notes",
        max_items=lim.max_plan_steps,
        max_len=lim.max_text_len,
    )
    raw_steps = d.get("steps") or []
    if not isinstance(raw_steps, list):
        raise ValidationError("steps must be a list")
    if len(raw_steps) > lim.max_plan_steps:
        raise ValidationError("too many plan steps")
    plan_id = ensure_id(d.get("id") or new_id("plan"), field="id")
    steps = [build_plan_step({**step, "plan_id": plan_id}, lim) for step in raw_steps]
    return Plan(
        id=plan_id,
        goal_entity_id=goal_entity_id,
        title=title,
        status=status,
        created_at=clamp_str(d.get("created_at") or utc_now_iso(), max_len=64, required=True, field="created_at"),
        updated_at=clamp_str(d.get("updated_at") or utc_now_iso(), max_len=64, required=True, field="updated_at"),
        source_id=source_id,
        confidence=confidence,
        assumptions=assumptions,
        constraints=constraints,
        risks=risks,
        approval_points=approval_points,
        verification_steps=verification_steps,
        rollback_notes=rollback_notes,
        steps=steps,
    )


def validate_confidence_category(category: Any) -> str:
    """Public alias for confidence category normalisation."""
    return categorize_confidence(category)


def validate_entity_type(entity_type: Any) -> str:
    return _enum(entity_type, allowed=ENTITY_TYPES, field="entity_type")


def validate_relation_type(relation_type: Any) -> str:
    return _enum(relation_type, allowed=RELATION_TYPES, field="relation_type")


def validate_status_value(status: Any, *, allowed: Optional[frozenset[str]] = None) -> str:
    return _enum(status, allowed=allowed or ENTITY_STATUSES, field="status")
