"""Cora Foundation — Phase 5.5 Agent Orchestrator / Scheduler.

Receives TaskGraph from Planner. Does not invent tasks.
Does not dispatch live capabilities. Schedules specialist AgentRuntime work.
Default OFF.
"""

from .config import OrchestratorConfig, ResourceHint
from .engine import AgentOrchestrator, get_orchestrator, reset_orchestrator_for_tests
from .flags import ENV_ENABLED, orchestrator_enabled_from_env
from .observe import GraphProgress, render_progress_bars

__all__ = [
    "ENV_ENABLED",
    "AgentOrchestrator",
    "GraphProgress",
    "OrchestratorConfig",
    "ResourceHint",
    "get_orchestrator",
    "orchestrator_enabled_from_env",
    "render_progress_bars",
    "reset_orchestrator_for_tests",
]
