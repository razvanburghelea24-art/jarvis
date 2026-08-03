"""Cora Foundation — Phase 5 Specialist Agents (result-only).

Agents execute plan *tasks* into AgentResult. They never dispatch,
never decide architecture, never take final Owner decisions.
Default OFF. Planner remains the boss.
"""

from .flags import ENV_ENABLED, agents_enabled_from_env
from .registry import AgentRegistry, default_agent_registry
from .runtime import AgentRuntime, get_agent_runtime, reset_agent_runtime_for_tests
from .task_graph import TaskGraph, TaskNode, TaskStatus, graph_from_plan
from .types import AgentResult, AgentRole, AgentResultStatus, QualityScores

__all__ = [
    "ENV_ENABLED",
    "AgentRegistry",
    "AgentResult",
    "AgentResultStatus",
    "AgentRole",
    "AgentRuntime",
    "QualityScores",
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "agents_enabled_from_env",
    "default_agent_registry",
    "get_agent_runtime",
    "graph_from_plan",
    "reset_agent_runtime_for_tests",
]
