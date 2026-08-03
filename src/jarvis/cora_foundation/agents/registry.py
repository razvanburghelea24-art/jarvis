"""Agent registry — specialists only."""

from __future__ import annotations

from .base import SpecialistAgent
from .code import CodeAgent
from .research import ResearchAgent
from .review import ReviewAgent
from .types import AgentRole
from .validation import ValidationAgent


class AgentRegistry:
    def __init__(self, agents: dict[AgentRole, SpecialistAgent] | None = None) -> None:
        self._agents = agents or {
            AgentRole.RESEARCH: ResearchAgent(),
            AgentRole.CODE: CodeAgent(),
            AgentRole.REVIEW: ReviewAgent(),
            AgentRole.VALIDATION: ValidationAgent(),
        }

    def get(self, role: AgentRole | str) -> SpecialistAgent | None:
        if isinstance(role, str):
            role = AgentRole(role)
        return self._agents.get(role)

    def roles(self) -> tuple[AgentRole, ...]:
        return tuple(sorted(self._agents.keys(), key=lambda r: r.value))


def default_agent_registry() -> AgentRegistry:
    return AgentRegistry()
