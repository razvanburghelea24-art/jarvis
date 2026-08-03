"""Cora Foundation — Phase 6A Computer Operator (Observability First).

Sees the desktop. Does not control it.
Control (6B) stays OFF until Owner GO + Planner → Scheduler → Approval → Policy → Dispatcher.
Operator never decides — Planner remains the brain.
"""

from .allowlist import AppAllowlist, DEFAULT_ALLOWLIST
from .engine import ComputerOperator, get_computer_operator, reset_computer_operator_for_tests
from .flags import (
    ENV_CONTROL_ENABLED,
    ENV_ENABLED,
    operator_control_enabled_from_env,
    operator_enabled_from_env,
)
from .preview import ActionPreview, PreviewStep
from .types import (
    IndicatorState,
    ObservationSnapshot,
    OperatorMode,
)

__all__ = [
    "ENV_CONTROL_ENABLED",
    "ENV_ENABLED",
    "ActionPreview",
    "AppAllowlist",
    "ComputerOperator",
    "DEFAULT_ALLOWLIST",
    "IndicatorState",
    "ObservationSnapshot",
    "OperatorMode",
    "PreviewStep",
    "get_computer_operator",
    "operator_control_enabled_from_env",
    "operator_enabled_from_env",
    "reset_computer_operator_for_tests",
]
