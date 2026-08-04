"""Framework Adapter — mock default · LIVE optional (READ before WRITE)."""

from .adapter import ADAPTER_ID, FrameworkAdapter
from .flags import (
    ENV_LIVE,
    ENV_PHASE,
    ENV_TOKEN,
    framework_live_enabled,
    framework_live_phase,
)
from .live_transport import LiveFrameworkTransport
from .path import FrameworkGatedResult, build_framework_transport, execute_framework_gated
from .transport import FrameworkTransport, FrameworkTransportResult, MockFrameworkTransport

__all__ = [
    "ADAPTER_ID",
    "ENV_LIVE",
    "ENV_PHASE",
    "ENV_TOKEN",
    "FrameworkAdapter",
    "FrameworkGatedResult",
    "FrameworkTransport",
    "FrameworkTransportResult",
    "LiveFrameworkTransport",
    "MockFrameworkTransport",
    "build_framework_transport",
    "execute_framework_gated",
    "framework_live_enabled",
    "framework_live_phase",
]
