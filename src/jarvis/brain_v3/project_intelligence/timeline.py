"""Build project timelines from Brain V3 timeline events."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..service import BrainV3Service


def build_timeline_from_events(
    events: List[Any],
    *,
    project_entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Normalise timeline events into ordered dicts for project intelligence."""
    normalised: List[Dict[str, Any]] = []
    for event in events:
        if hasattr(event, "to_dict"):
            data = event.to_dict()
        elif isinstance(event, dict):
            data = dict(event)
        else:
            continue
        entry = {
            "id": data.get("id"),
            "event_type": data.get("event_type"),
            "title": data.get("title"),
            "description": data.get("description", ""),
            "occurred_at": data.get("occurred_at"),
            "entity_ids": list(data.get("entity_ids") or []),
            "confidence": data.get("confidence", 0.5),
            "metadata": dict(data.get("metadata") or {}),
        }
        if project_entity_id and project_entity_id not in entry["entity_ids"]:
            entry["metadata"]["indirect"] = True
        normalised.append(entry)

    return sorted(normalised, key=lambda item: (item.get("occurred_at") or "", item.get("id") or ""))


def build_project_timeline(
    brain_v3_service: "BrainV3Service",
    project_entity_id: str,
    *,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Fetch and normalise timeline events for a project entity."""
    events = brain_v3_service._timeline.project_timeline(project_entity_id, limit=limit)
    return build_timeline_from_events(events, project_entity_id=project_entity_id)
