"""Code Agent — implements proposals only. Does not decide."""

from __future__ import annotations

from typing import Any

from .base import SpecialistAgent
from .task_graph import TaskNode
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores


class CodeAgent(SpecialistAgent):
    role = AgentRole.CODE

    def run(self, task: TaskNode, *, context: dict[str, Any] | None = None) -> AgentResult:
        ctx = context or {}
        capability = task.capability or (ctx.get("capability") if ctx else None)
        # Stub implementation artifact — never writes files / never dispatches.
        proposal = {
            "kind": "proposed_change",
            "capability": capability,
            "applied": False,
            "writes_files": False,
            "note": "Code Agent proposes implementation; Policy-gated dispatch applies later.",
        }
        findings = [
            "Implementation proposal prepared (not applied).",
            "Code Agent does not decide architecture or approvals.",
        ]
        if capability:
            findings.append(f"Maps to capability: {capability}")

        confidence = 0.55 if capability else 0.40
        quality = QualityScores(
            architecture=0.45,  # does not own architecture
            security=0.50,
            performance=0.50,
            complexity=0.55,
            maintainability=0.50,
        )
        return self._result(
            task,
            status=AgentResultStatus.COMPLETED,
            summary=f"Code task finished for '{task.title}'. Proposal only — not applied.",
            findings=findings,
            artifacts={"proposal": proposal},
            confidence=confidence,
            quality=quality,
            proposed_capabilities=[capability] if capability else [],
            recommends_review=True,  # code always benefits from review
        )
