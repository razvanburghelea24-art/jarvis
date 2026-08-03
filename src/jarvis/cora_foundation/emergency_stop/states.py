"""Safety modes and trigger sources — labels only."""

from __future__ import annotations

from enum import Enum


class SafetyMode(str, Enum):
    NORMAL = "NORMAL"
    SAFE_MODE = "SAFE_MODE"
    ESTOP_MANUAL = "ESTOP_MANUAL"
    ESTOP_POLICY = "ESTOP_POLICY"
    ESTOP_SECURITY = "ESTOP_SECURITY"
    ESTOP_RUNTIME = "ESTOP_RUNTIME"
    RECOVERY = "RECOVERY"


class TriggerSource(str, Enum):
    OWNER = "owner"
    POLICY = "policy"
    SENTINEL = "sentinel"
    RUNTIME = "runtime"
    WATCHDOG = "watchdog"
    SYSTEM = "system"


def is_estop_mode(mode: SafetyMode) -> bool:
    return mode in {
        SafetyMode.ESTOP_MANUAL,
        SafetyMode.ESTOP_POLICY,
        SafetyMode.ESTOP_SECURITY,
        SafetyMode.ESTOP_RUNTIME,
    }
