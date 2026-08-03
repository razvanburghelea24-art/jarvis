"""Specialist agent base — produce AgentResult only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .task_graph import TaskNode
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores, clamp01, new_result_id


class SpecialistAgent(ABC):
    """One purpose. No dispatch. No final decisions. No architecture ownership."""

    role: AgentRole

    @abstractmethod
    def run(
        self,
        task: TaskNode,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        raise NotImplementedError

    def _result(
        self,
        task: TaskNode,
        *,
        status: AgentResultStatus,
        summary: str,
        findings: list[str] | None = None,
        artifacts: dict[str, Any] | None = None,
        confidence: float,
        quality: QualityScores | None = None,
        proposed_capabilities: list[str] | None = None,
        recommends_review: bool = False,
    ) -> AgentResult:
        return AgentResult(
            result_id=new_result_id(),
            agent_role=self.role,
            task_id=task.task_id,
            plan_id=task.plan_id,
            status=status,
            summary=summary,
            findings=tuple(findings or ()),
            artifacts=dict(artifacts or {}),
            confidence=clamp01(confidence),
            quality=quality or QualityScores(),
            proposed_capabilities=tuple(proposed_capabilities or ()),
            recommends_review=recommends_review,
            dispatches=False,
            decides_architecture=False,
            final_decision=False,
        )
