"""Injectable runtime state for Live Execution Gateway checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

from .decision import ExecutionMode

# Default capabilities permitted when context.allowed_capabilities is None
DEFAULT_ALLOWED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "github.write",
        "github.read",
        "discord.send",
        "discord.read",
        "framework.execute",
        "framework.read",
        "railway.deploy",
        "railway.read",
        "n8n.execute",
        "n8n.read",
        "filesystem.write",
        "filesystem.read",
    }
)

# Writes blocked under Safe Mode
WRITE_CAPABILITIES: frozenset[str] = frozenset(
    {
        "github.write",
        "discord.send",
        "framework.execute",
        "railway.deploy",
        "n8n.execute",
        "filesystem.write",
        "computer_operator.control",
    }
)


@dataclass
class GatewayContext:
    """Read-only snapshot of safety / session state for one evaluate() call."""

    session_id: str = ""
    workspace_id: str = ""
    session_valid: bool = True
    workspace_active: bool = True
    e_stop: bool = False
    kill_switch: bool = False
    safe_mode: bool = False
    rate_limit_ok: bool = True
    audit_available: bool = True
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    allowed_capabilities: FrozenSet[str] | None = None
    # When True, audit.record() would fail even if available flag is True
    audit_record_ok: bool = True
    metadata: dict = field(default_factory=dict)

    def permitted_capabilities(self) -> frozenset[str]:
        if self.allowed_capabilities is None:
            return DEFAULT_ALLOWED_CAPABILITIES
        return frozenset(self.allowed_capabilities)
