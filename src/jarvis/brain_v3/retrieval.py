"""Read-only context retrieval for Brain V3 Phase 1."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from .errors import NotFoundError
from .limits import BrainV3Limits
from .models import Entity, Relation, SourceRecord, TimelineEvent

_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokenize(query: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(query or "")]


def _entity_matches(entity: Entity, tokens: List[str]) -> bool:
    if not tokens:
        return True
    haystacks = [
        entity.display_name.lower(),
        entity.canonical_name.lower(),
        entity.description.lower(),
        " ".join(alias.lower() for alias in entity.aliases),
    ]
    joined = " ".join(haystacks)
    return any(token in joined for token in tokens)


def _event_matches(event: TimelineEvent, tokens: List[str]) -> bool:
    if not tokens:
        return True
    haystack = " ".join(
        [
            event.title.lower(),
            event.description.lower(),
            event.event_type.lower(),
        ]
    )
    return any(token in haystack for token in tokens)


def _confidence_sort_key(entity: Entity) -> tuple[float, str]:
    return (-entity.confidence, entity.id)


def retrieve_context(
    repo: Any,
    query: str,
    *,
    entity_types: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    min_confidence: float = 0.0,
    max_results: Optional[int] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limits: BrainV3Limits | None = None,
) -> Dict[str, Any]:
    """Read-only bounded retrieval over entities, relations, timeline, and sources."""
    lim = limits or BrainV3Limits()
    result_cap = max_results if max_results is not None else lim.max_retrieval_results
    result_cap = min(max(1, result_cap), lim.max_retrieval_results)
    tokens = _tokenize(query)

    allowed_types: Optional[Set[str]] = set(entity_types) if entity_types else None
    project_entity_ids: Optional[Set[str]] = None
    if project_id:
        try:
            repo.get_entity(project_id)
        except NotFoundError:
            project_entity_ids = None
        else:
            project_entity_ids = {project_id}
            for neighbor, relation in repo.neighbors(project_id, limit=lim.max_batch_size):
                if relation.status == "active":
                    project_entity_ids.add(neighbor.id)

    entities: List[Entity] = []
    reasons: List[str] = []
    for entity in repo.list_entities(status="active", limit=lim.max_batch_size):
        if entity.confidence < min_confidence:
            continue
        if allowed_types is not None and entity.entity_type not in allowed_types:
            continue
        if project_entity_ids is not None and entity.id not in project_entity_ids:
            continue
        if not _entity_matches(entity, tokens):
            continue
        entities.append(entity)
        reasons.append(f"entity:{entity.id}:matched query tokens")

    entities.sort(key=_confidence_sort_key)
    entities = entities[:result_cap]

    entity_ids = {entity.id for entity in entities}
    relations: List[Relation] = []
    for entity in entities:
        for neighbor, relation in repo.neighbors(entity.id, limit=lim.max_batch_size):
            if relation.status != "active":
                continue
            if relation.source_entity_id in entity_ids or relation.target_entity_id in entity_ids:
                if relation not in relations:
                    relations.append(relation)
                    reasons.append(f"relation:{relation.id}:connected to matched entity")

    timeline_events: List[TimelineEvent] = []
    raw_events = repo.list_timeline_events(limit=lim.max_batch_size)
    for event in raw_events:
        if time_from is not None and event.occurred_at < time_from:
            continue
        if time_to is not None and event.occurred_at > time_to:
            continue
        if event.confidence < min_confidence:
            continue
        if project_entity_ids is not None and not any(eid in project_entity_ids for eid in event.entity_ids):
            continue
        if not _event_matches(event, tokens):
            continue
        timeline_events.append(event)
        reasons.append(f"timeline:{event.id}:matched query tokens")
    timeline_events = sorted(timeline_events, key=lambda event: (-event.confidence, event.id))[:result_cap]

    sources: List[SourceRecord] = []
    seen_sources: Set[str] = set()
    for entity in entities:
        if entity.source_id and entity.source_id not in seen_sources:
            try:
                source = repo.get_source(entity.source_id)
            except NotFoundError:
                continue
            sources.append(source)
            seen_sources.add(source.id)
            reasons.append(f"source:{source.id}:entity provenance")
    for event in timeline_events:
        if event.source_id and event.source_id not in seen_sources:
            try:
                source = repo.get_source(event.source_id)
            except NotFoundError:
                continue
            sources.append(source)
            seen_sources.add(source.id)
            reasons.append(f"source:{source.id}:timeline provenance")

    return {
        "entities": entities,
        "relations": relations[:result_cap],
        "timeline_events": timeline_events,
        "sources": sources[:result_cap],
        "reasons": reasons[: result_cap * 4],
    }
