"""Suggested next steps for a project (non-executable, approval required)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import new_id


def _base_step(
    title: str,
    *,
    description: str = "",
    rationale: str = "",
    source: str = "inferred",
    priority: str = "medium",
    project_entity_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": new_id("nstep"),
        "title": title,
        "description": description,
        "rationale": rationale,
        "source": source,
        "priority": priority,
        "project_entity_id": project_entity_id,
        "requires_approval": True,
        "execution_forbidden": True,
    }


def suggest_next_steps(
    *,
    blockers: List[Dict[str, Any]],
    milestones: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    project_entity_id: Optional[str] = None,
    open_goals: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Suggest read-only next steps from project signals. Never executable."""
    steps: List[Dict[str, Any]] = []

    for blocker in blockers[:5]:
        steps.append(
            _base_step(
                f"Review blocker: {blocker.get('title', 'unknown')}",
                description=str(blocker.get("description") or ""),
                rationale="Active blocker detected in project intelligence snapshot",
                source="blocker",
                priority=str(blocker.get("severity") or "high"),
                project_entity_id=project_entity_id,
            )
        )

    for goal in (open_goals or [])[:5]:
        name = goal.get("display_name") or goal.get("canonical_name") or goal.get("title") or "goal"
        steps.append(
            _base_step(
                f"Clarify goal status: {name}",
                description=str(goal.get("description") or ""),
                rationale="Open goal entity linked to project",
                source="goal",
                priority="medium",
                project_entity_id=project_entity_id,
            )
        )

    if not milestones and timeline:
        steps.append(
            _base_step(
                "Record project milestones",
                description="No milestones detected in the project timeline yet.",
                rationale="Timeline exists but contains no milestone events",
                source="assistant_suggested",
                priority="low",
                project_entity_id=project_entity_id,
            )
        )

    if not blockers and not steps:
        steps.append(
            _base_step(
                "Review project snapshot",
                description="No blockers or urgent signals detected.",
                rationale="Default advisory step when project state is unclear",
                source="assistant_suggested",
                priority="low",
                project_entity_id=project_entity_id,
            )
        )

    return steps
