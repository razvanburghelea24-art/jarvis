"""Live Execution Gateway — DispatchRequest → GatewayDecision (never execute).

Law: No Integration Layer call without Gateway ALLOW.
"""

from .context import (
    DEFAULT_ALLOWED_CAPABILITIES,
    WRITE_CAPABILITIES,
    GatewayContext,
)
from .decision import (
    CheckResult,
    ExecutionMode,
    GatewayDecision,
    GatewayVerdict,
)
from .gateway import CHECK_ORDER, LiveExecutionGateway

__all__ = [
    "CHECK_ORDER",
    "DEFAULT_ALLOWED_CAPABILITIES",
    "WRITE_CAPABILITIES",
    "CheckResult",
    "ExecutionMode",
    "GatewayContext",
    "GatewayDecision",
    "GatewayVerdict",
    "LiveExecutionGateway",
]
