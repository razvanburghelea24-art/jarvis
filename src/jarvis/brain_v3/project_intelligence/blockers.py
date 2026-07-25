"""Blocker detection from project graph and timeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..service import BrainV3Service

_BLOCKED_RELATIONS = frozenset({"blocked_by"})
_BLOCKED_STEP_STATUSES = frozenset({"blocked", "cancelled"})
_BLOCKED_PLAN_STATUSES = frozenset({"blocked"})


def detect_blockers_from_timeline(
    timeline: List[Dict[str, Any]],
    *,
    project_entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Find blocker signals in timeline events."""
    blockers: List[Dict[str, Any]] = []
    for index, event in enumerate(timeline):
        event_type = str(event.get("event_type") or "").lower()
        title = str(event.get("title") or "").strip()
        metadata = dict(event.get("metadata") or {})
        if event_type == "blocker" or metadata.get("blocker") or "blocked" in title.lower():
            blockers.append(
                {
                    "id": event.get("id") or f"blocker_evt_{index}",
                    "title": title or "Unnamed blocker",
                    "description": event.get("description", ""),
                    "occurred_at": event.get("occurred_at"),
                    "source": "timeline",
                    "severity": metadata.get("severity", "medium"),
                    "entity_ids": list(event.get("entity_ids") or []),
                    "project_entity_id": project_entity_id,
                    "requires_approval": True,
                    "execution_forbidden": True,
                }
            )
    return blockers


def detect_blockers_from_graph(
    brain_v3_service: "BrainV3Service",
    project_entity_id: str,
    *,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Find active blocked_by relations involving the project."""
    blockers: List[Dict[str, Any]] = []
    neighbors: List[Tuple[Any, Any]] = brain_v3_service.get_neighbors(project_entity_id, limit=limit)
    for neighbor, relation in neighbors:
        if relation.relation_type not in _BLOCKED_RELATIONS:
            continue
        if relation.status != "active":
            continue
        blockers.append(
            {
                "id": relation.id,
                "title": f"Blocked by {neighbor.display_name or neighbor.canonical_name}",
                "description": neighbor.description or "",
                "source": "graph",
                "severity": "high",
                "relation_type": relation.relation_type,
                "blocking_entity_id": neighbor.id,
                "project_entity_id": project_entity_id,
                "requires_approval": True,
                "execution_forbidden": True,
            }
        )
    return blockers


def detect_blockers_from_plans(
    brain_v3_service: "BrainV3Service",
    *,
    project_entity_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Find blocked plan steps linked to a project goal entity."""
    if project_entity_id is None:
        return []
    blockers: List[Dict[str, Any]] = []
    repo = brain_v3_service.repo
    for plan in repo.list_plans(limit=limit):
        if plan.goal_entity_id != project_entity_id:
            continue
        if plan.status in _BLOCKED_PLAN_STATUSES:
            blockers.append(
                {
                    "id": plan.id,
                    "title": f"Plan blocked: {plan.title}",
                    "description": "; ".join(plan.risks[:3]),
                    "source": "plan",
                    "severity": "high",
                    "plan_id": plan.id,
                    "project_entity_id": project_entity_id,
                    "requires_approval": True,
                    "execution_forbidden": True,
                }
            )
        for step in plan.steps:
            if step.status not in _BLOCKED_STEP_STATUSES:
                continue
            blockers.append(
                {
                    "id": step.id,
                    "title": f"Step blocked: {step.title}",
                    "description": step.description,
                    "source": "plan_step",
                    "severity": "medium",
                    "plan_id": plan.id,
                    "project_entity_id": project_entity_id,
                    "requires_approval": True,
                    "execution_forbidden": True,
                }
            )
    return blockers
