"""Project intelligence service (read-mostly, Phase 2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..errors import NotFoundError, ValidationError
from ..models import normalize_key
from .blockers import (
    detect_blockers_from_graph,
    detect_blockers_from_plans,
    detect_blockers_from_timeline,
)
from .milestones import detect_milestones
from .next_steps import suggest_next_steps
from .state import ProjectSnapshot
from .summary import build_summary
from .timeline import build_project_timeline, build_timeline_from_events

if TYPE_CHECKING:
    from ..service import BrainV3Service


class ProjectIntelligenceService:
    """Assemble project snapshots from Brain V3 without mutating graph state."""

    def __init__(self, brain_v3_service: Optional["BrainV3Service"] = None) -> None:
        self._brain_v3 = brain_v3_service

    @property
    def brain_v3(self) -> Optional["BrainV3Service"]:
        return self._brain_v3

    def _require_brain_v3(self) -> "BrainV3Service":
        if self._brain_v3 is None:
            raise ValidationError("brain_v3 service required for project intelligence")
        return self._brain_v3

    def _resolve_project(self, project_name_or_id: str) -> Any:
        service = self._require_brain_v3()
        key = normalize_key(project_name_or_id)
        try:
            return service.get_entity(project_name_or_id)
        except NotFoundError:
            pass

        matches = service.find_entities(query=project_name_or_id, entity_type="project", limit=20)
        for entity in matches:
            if entity.id == project_name_or_id:
                return entity
            if entity.canonical_name == key:
                return entity
            if normalize_key(entity.display_name) == key:
                return entity
        if matches:
            return matches[0]
        raise NotFoundError(f"project not found: {project_name_or_id}")

    def build_timeline(self, project_name_or_id: str, *, limit: int = 200) -> List[Dict[str, Any]]:
        project = self._resolve_project(project_name_or_id)
        return build_project_timeline(self._require_brain_v3(), project.id, limit=limit)

    def detect_blockers(self, project_name_or_id: str) -> List[Dict[str, Any]]:
        project = self._resolve_project(project_name_or_id)
        service = self._require_brain_v3()
        timeline = self.build_timeline(project.id)
        blockers: List[Dict[str, Any]] = []
        blockers.extend(detect_blockers_from_timeline(timeline, project_entity_id=project.id))
        blockers.extend(detect_blockers_from_graph(service, project.id))
        blockers.extend(detect_blockers_from_plans(service, project_entity_id=project.id))
        return blockers

    def suggest_next_steps(self, project_name_or_id: str) -> List[Dict[str, Any]]:
        project = self._resolve_project(project_name_or_id)
        timeline = self.build_timeline(project.id)
        milestones = detect_milestones(timeline, project_entity_id=project.id)
        blockers = self.detect_blockers(project.id)
        open_goals = self._open_goal_entities(project.id)
        return suggest_next_steps(
            blockers=blockers,
            milestones=milestones,
            timeline=timeline,
            project_entity_id=project.id,
            open_goals=open_goals,
        )

    def _open_goal_entities(self, project_entity_id: str) -> List[Dict[str, Any]]:
        service = self._require_brain_v3()
        goals: List[Dict[str, Any]] = []
        for neighbor, relation in service.get_neighbors(project_entity_id, limit=100):
            if relation.relation_type in {"targets", "part_of", "related_to"} and neighbor.entity_type == "goal":
                if neighbor.status == "active":
                    goals.append(neighbor.to_dict())
        return goals

    def build_snapshot(self, project_name_or_id: str) -> ProjectSnapshot:
        project = self._resolve_project(project_name_or_id)
        service = self._require_brain_v3()
        timeline = build_project_timeline(service, project.id)
        milestones = detect_milestones(timeline, project_entity_id=project.id)
        blockers = self.detect_blockers(project.id)
        next_steps = self.suggest_next_steps(project.id)
        related_entities = [
            neighbor.to_dict()
            for neighbor, relation in service.get_neighbors(project.id, limit=50)
            if relation.status == "active"
        ]
        summary = build_summary(
            entity=project.to_dict(),
            related_entities=related_entities,
            milestones=milestones,
            blockers=blockers,
            next_steps=next_steps,
        )
        return ProjectSnapshot(
            project_id=project.id,
            project_name=project.display_name or project.canonical_name,
            entity=project.to_dict(),
            related_entities=related_entities,
            timeline=timeline,
            milestones=milestones,
            blockers=blockers,
            next_steps=next_steps,
            summary=summary,
        )
