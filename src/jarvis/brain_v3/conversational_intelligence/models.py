"""Conversational intelligence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..errors import ValidationError
from ..models import new_id, utc_now_iso


@dataclass
class AnswerSupport:
    supported_facts: List[str] = field(default_factory=list)
    user_preferences: List[str] = field(default_factory=list)
    project_state: Dict[str, Any] = field(default_factory=dict)
    relevant_decisions: List[str] = field(default_factory=list)
    recent_events: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    recommended_citations: List[str] = field(default_factory=list)
    prohibited_claims: List[str] = field(default_factory=list)
    execution_forbidden: bool = True
    generated_at: str = field(default_factory=utc_now_iso)
    support_id: str = ""

    def __post_init__(self) -> None:
        self.execution_forbidden = True
        if not self.support_id:
            self.support_id = new_id("ans")
        for field_name in (
            "supported_facts",
            "user_preferences",
            "relevant_decisions",
            "recent_events",
            "uncertainties",
            "recommended_citations",
            "prohibited_claims",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, list):
                raise ValidationError(f"{field_name} must be a list")
        if not isinstance(self.project_state, dict):
            raise ValidationError("project_state must be a dict")
        if not isinstance(self.contradictions, list):
            raise ValidationError("contradictions must be a list")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "support_id": self.support_id,
            "supported_facts": list(self.supported_facts),
            "user_preferences": list(self.user_preferences),
            "project_state": dict(self.project_state),
            "relevant_decisions": list(self.relevant_decisions),
            "recent_events": list(self.recent_events),
            "contradictions": list(self.contradictions),
            "uncertainties": list(self.uncertainties),
            "recommended_citations": list(self.recommended_citations),
            "prohibited_claims": list(self.prohibited_claims),
            "execution_forbidden": True,
            "generated_at": self.generated_at,
        }


@dataclass
class MemoryPolicy:
    approved_only: bool = True
    include_inferences: bool = False
    include_sensitive: bool = False
    read_only: bool = True

    def __post_init__(self) -> None:
        self.read_only = True
