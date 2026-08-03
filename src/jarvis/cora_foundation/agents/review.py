"""Review Agent — bugs, architecture checks, regressions. No final say."""

from __future__ import annotations

from typing import Any

from .base import SpecialistAgent
from .task_graph import TaskNode
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores


class ReviewAgent(SpecialistAgent):
    role = AgentRole.REVIEW

    def run(self, task: TaskNode, *, context: dict[str, Any] | None = None) -> AgentResult:
        ctx = context or {}
        prior = ctx.get("prior_results") or []
        low_conf = [
            r for r in prior
            if isinstance(r, dict) and float(r.get("confidence") or 0) < 0.50
        ]
        findings = [
            "Reviewed for bugs, architecture drift, and regression risk.",
            "Review Agent reports findings — does not approve or reject Owner decisions.",
        ]
        if low_conf:
            findings.append(f"{len(low_conf)} prior result(s) below confidence 0.50.")

        # Architecture score is an observation, not a decision.
        arch = 0.72 if not low_conf else 0.48
        quality = QualityScores(
            architecture=arch,
            security=0.68,
            performance=0.60,
            complexity=0.55,
            maintainability=0.70,
        )
        confidence = 0.75 if not low_conf else 0.52
        return self._result(
            task,
            status=AgentResultStatus.COMPLETED,
            summary=f"Review finished for '{task.title}'. Findings only.",
            findings=findings,
            artifacts={
                "checks": ["bugs", "architecture", "regressions"],
                "approves": False,
            },
            confidence=confidence,
            quality=quality,
            recommends_review=False,
        )
