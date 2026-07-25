"""Milestone detection from project timeline and graph."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_MILESTONE_EVENT_TYPES = frozenset(
    {
        "milestone",
        "release",
        "decision",
        "goal_completed",
        "phase_complete",
    }
)


def detect_milestones(
    timeline: List[Dict[str, Any]],
    *,
    project_entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract milestone-like events from a normalised project timeline."""
    milestones: List[Dict[str, Any]] = []
    for index, event in enumerate(timeline):
        event_type = str(event.get("event_type") or "").lower()
        title = str(event.get("title") or "").strip()
        if not title:
            continue
        is_milestone = event_type in _MILESTONE_EVENT_TYPES
        if not is_milestone and "milestone" in title.lower():
            is_milestone = True
        if not is_milestone:
            continue
        milestones.append(
            {
                "id": event.get("id") or f"milestone_{index}",
                "title": title,
                "description": event.get("description", ""),
                "occurred_at": event.get("occurred_at"),
                "event_type": event_type or "milestone",
                "entity_ids": list(event.get("entity_ids") or []),
                "confidence": event.get("confidence", 0.5),
                "source": "timeline",
                "project_entity_id": project_entity_id,
                "requires_approval": True,
                "execution_forbidden": True,
            }
        )
    return milestones
