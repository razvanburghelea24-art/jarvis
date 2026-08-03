"""Cora Foundation — Phase 4 AI Planner (PLAN-ONLY).

Observes context and builds Execution Plans. Never executes.
Default OFF. No live APIs. Memory read via snapshot input only.
"""

from .context import PlannerContext
from .engine import PlannerEngine, get_planner_engine, reset_planner_engine_for_tests
from .flags import ENV_ENABLED, planner_enabled_from_env
from .types import Plan, PlanKind, PlanRiskLevel, PlanStatus, PlanStep

__all__ = [
    "ENV_ENABLED",
    "Plan",
    "PlanKind",
    "PlanRiskLevel",
    "PlanStatus",
    "PlanStep",
    "PlannerContext",
    "PlannerEngine",
    "get_planner_engine",
    "planner_enabled_from_env",
    "reset_planner_engine_for_tests",
]
