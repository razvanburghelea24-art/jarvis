"""Validation Agent — tests, checks, compliance. Not Owner approval."""

from __future__ import annotations

from typing import Any

from .base import SpecialistAgent
from .task_graph import TaskNode
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores


class ValidationAgent(SpecialistAgent):
    role = AgentRole.VALIDATION

    def run(self, task: TaskNode, *, context: dict[str, Any] | None = None) -> AgentResult:
        ctx = context or {}
        prior = ctx.get("prior_results") or []
        recommends = any(
            isinstance(r, dict) and r.get("recommends_review") for r in prior
        )
        findings = [
            "Validation: tests / checks / compliance (contract-level stub).",
            "Does not replace Owner Approval or Dispatcher Policy.",
        ]
        if recommends:
            findings.append("Prior agents recommended further review.")

        confidence = 0.70 if not recommends else 0.58
        quality = QualityScores(
            architecture=0.60,
            security=0.75,
            performance=0.65,
            complexity=0.50,
            maintainability=0.68,
        )
        return self._result(
            task,
            status=AgentResultStatus.COMPLETED,
            summary=f"Validation finished for '{task.title}'. Compliance report only.",
            findings=findings,
            artifacts={
                "checks": ["tests", "verification", "compliance"],
                "owner_approval_required": True,
                "dispatched": False,
            },
            confidence=confidence,
            quality=quality,
            recommends_review=recommends,
        )
