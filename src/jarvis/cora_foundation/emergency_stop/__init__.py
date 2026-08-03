"""Cora Foundation — Phase 1E Emergency Stop.

E-Stop does not stop Cora — it stops action execution.
Default OFF until runtime integration (CORA_ESTOP_ENABLED).
"""

from .engine import EmergencyStopEngine, get_emergency_stop, reset_emergency_stop_for_tests
from .flags import ENV_ENABLED, estop_enabled_from_env
from .states import SafetyMode, TriggerSource
from .policy_gate import ActionClass, classify_capability, is_allowed_under_safety

__all__ = [
    "ENV_ENABLED",
    "ActionClass",
    "EmergencyStopEngine",
    "SafetyMode",
    "TriggerSource",
    "classify_capability",
    "estop_enabled_from_env",
    "get_emergency_stop",
    "is_allowed_under_safety",
    "reset_emergency_stop_for_tests",
]
