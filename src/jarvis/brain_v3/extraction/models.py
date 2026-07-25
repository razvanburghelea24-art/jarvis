"""Memory candidate models for Brain V3 Phase 2 extraction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

CANDIDATE_TYPES = frozenset(
    {
        "preference",
        "project",
        "decision",
        "goal",
        "task",
        "event",
        "constraint",
        "entity",
    }
)
RECOMMENDED_ACTIONS = frozenset(
    {"create", "update", "supersede", "merge", "ignore", "needs_review"}
)
SENSITIVITY_LEVELS = frozenset({"normal", "blocked", "sensitive"})
CONTRADICTION_STATES = frozenset(
    {"none", "potential", "confirmed", "superseded", "evolution"}
)


def new_candidate_id() -> str:
    return f"cand_{uuid.uuid4().hex[:16]}"


@dataclass
class MemoryCandidate:
    candidate_id: str
    candidate_type: str
    normalized_value: str
    display_value: str
    source_message_ids: List[str]
    confidence: float
    reason: str
    recommended_action: str
    source_id: Optional[str] = None
    temporal_scope: str = "unspecified"
    project_scope: str = ""
    sensitivity: str = "normal"
    contradiction_state: str = "none"
    existing_memory_matches: List[str] = field(default_factory=list)
    requires_approval: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.requires_approval = True
        if self.candidate_type not in CANDIDATE_TYPES:
            self.candidate_type = "entity"
        if self.recommended_action not in RECOMMENDED_ACTIONS:
            self.recommended_action = "needs_review"
        if self.sensitivity not in SENSITIVITY_LEVELS:
            self.sensitivity = "normal"
        if self.contradiction_state not in CONTRADICTION_STATES:
            self.contradiction_state = "none"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "normalized_value": self.normalized_value,
            "display_value": self.display_value,
            "source_message_ids": list(self.source_message_ids),
            "source_id": self.source_id,
            "confidence": self.confidence,
            "reason": self.reason,
            "temporal_scope": self.temporal_scope,
            "project_scope": self.project_scope,
            "sensitivity": self.sensitivity,
            "contradiction_state": self.contradiction_state,
            "existing_memory_matches": list(self.existing_memory_matches),
            "recommended_action": self.recommended_action,
            "requires_approval": True,
            "metadata": dict(self.metadata),
        }
