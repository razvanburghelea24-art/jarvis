"""Project intelligence snapshot state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import utc_now_iso


@dataclass
class ProjectSnapshot:
    """Read-only view of project knowledge assembled from Brain V3 graph and timeline."""

    project_id: str
    project_name: str
    entity: Optional[Dict[str, Any]] = None
    related_entities: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    next_steps: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    built_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "entity": self.entity,
            "related_entities": list(self.related_entities),
            "timeline": list(self.timeline),
            "milestones": list(self.milestones),
            "blockers": list(self.blockers),
            "next_steps": list(self.next_steps),
            "summary": {key: list(values) for key, values in self.summary.items()},
            "metadata": self.metadata,
            "built_at": self.built_at,
        }
