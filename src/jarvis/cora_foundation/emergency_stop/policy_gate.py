"""Classify capabilities: what E-Stop blocks vs allows."""

from __future__ import annotations

from enum import Enum

from .states import SafetyMode, is_estop_mode


class ActionClass(str, Enum):
    READ_DIAGNOSTIC = "read_diagnostic"  # always allowed
    EXTERNAL_WRITE = "external_write"  # blocked in SAFE_MODE and E-Stop
    INTERNAL_WRITE = "internal_write"  # blocked in E-Stop; allowed in SAFE_MODE with care


# Capabilities that remain available under E-Stop / Safe Mode.
_READ_DIAGNOSTIC = frozenset(
    {
        "Identity.whoami",
        "Memory.read",
        "OwnerProfile.read",
        "Workspace.scan",
        "Computer.observe",
    }
)

_EXTERNAL_WRITE = frozenset(
    {
        "Discord.send",
        "Overlay.refresh",  # treat as external UI write for safety
        "GitHub.create_pr",
        "Railway.deploy",
        "Server.restart",
        "OwnerProfile.write",
        "Memory.write",
        "Computer.click",
        "Computer.type_keys",
        "Computer.move_mouse",
        "Computer.open_app",
        "Computer.close_app",
        "Computer.write_clipboard",
        "Computer.automate",
        "Computer.execute_preview",
    }
)


def classify_capability(name: str) -> ActionClass:
    if name in _READ_DIAGNOSTIC:
        return ActionClass.READ_DIAGNOSTIC
    if name in _EXTERNAL_WRITE:
        return ActionClass.EXTERNAL_WRITE
    # Unknown capabilities are treated as external writes (fail-closed).
    return ActionClass.EXTERNAL_WRITE


def is_allowed_under_safety(capability: str, mode: SafetyMode) -> bool:
    """Return True if Dispatcher may invoke this capability under current safety mode."""
    kind = classify_capability(capability)
    if kind == ActionClass.READ_DIAGNOSTIC:
        return True
    if mode == SafetyMode.NORMAL:
        return True
    if mode == SafetyMode.RECOVERY:
        # Recovery: only diagnostics until Owner completes release.
        return kind == ActionClass.READ_DIAGNOSTIC
    if mode == SafetyMode.SAFE_MODE:
        # Safe mode blocks external effects; internal writes still blocked by default.
        return False
    if is_estop_mode(mode):
        return False
    return False
