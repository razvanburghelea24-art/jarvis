"""Cora Foundation — Phase 4 AI Planner (PLAN-ONLY) + Planner Routing.

PlannerEngine: builds Execution Plans (never executes).
PlannerRouter: decides if a plan is needed (PlannerDecision only).
"""

from .context import PlannerContext
from .engine import PlannerEngine, get_planner_engine, reset_planner_engine_for_tests
from .flags import ENV_ENABLED, planner_enabled_from_env
from .routing import PlannerRouter
from .routing_decision import (
    KIND_DECISION,
    SCHEMA_FAMILY,
    SCHEMA_VERSION,
    PlannerDecision,
    PlannerRisk,
    PlannerRoute,
)
from .types import Plan, PlanKind, PlanRiskLevel, PlanStatus, PlanStep

__all__ = [
    "ENV_ENABLED",
    "KIND_DECISION",
    "Plan",
    "PlanKind",
    "PlanRiskLevel",
    "PlanStatus",
    "PlanStep",
    "PlannerContext",
    "PlannerDecision",
    "PlannerEngine",
    "PlannerRisk",
    "PlannerRoute",
    "PlannerRouter",
    "SCHEMA_FAMILY",
    "SCHEMA_VERSION",
    "get_planner_engine",
    "planner_enabled_from_env",
    "reset_planner_engine_for_tests",
]
