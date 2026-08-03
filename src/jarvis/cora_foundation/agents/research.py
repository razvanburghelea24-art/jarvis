"""Research Agent — read, compare, research, explain. Never modifies."""

from __future__ import annotations

from typing import Any

from .base import SpecialistAgent
from .task_graph import TaskNode
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores


class ResearchAgent(SpecialistAgent):
    role = AgentRole.RESEARCH

    def run(self, task: TaskNode, *, context: dict[str, Any] | None = None) -> AgentResult:
        ctx = context or {}
        hub_n = int(ctx.get("integration_count") or len(ctx.get("integration_snapshots") or []))
        mem_n = int((ctx.get("memory_snapshot") or {}).get("record_count") or ctx.get("memory_records") or 0)
        has_identity = bool(ctx.get("identity") or ctx.get("who"))

        findings = [
            "Read-only research: compare available snapshots.",
            f"integration_snapshots={hub_n}",
            f"memory_records={mem_n}",
            f"identity_present={has_identity}",
        ]
        # Confidence rises with observable context richness.
        confidence = 0.35
        if has_identity:
            confidence += 0.15
        if hub_n:
            confidence += min(0.25, 0.08 * hub_n)
        if mem_n:
            confidence += min(0.20, 0.02 * mem_n)
        confidence = min(0.92, confidence)

        quality = QualityScores(
            architecture=0.55,
            security=0.70,  # read-only path
            performance=0.60,
            complexity=0.40,
            maintainability=0.65,
        )
        return self._result(
            task,
            status=AgentResultStatus.COMPLETED,
            summary=f"Research finished for task '{task.title}'. No mutations.",
            findings=findings,
            artifacts={
                "mode": "read_compare_explain",
                "mutates": False,
            },
            confidence=confidence,
            quality=quality,
            recommends_review=confidence < 0.50,
        )
