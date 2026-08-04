"""Railway Adapter — mock default · LIVE optional (infra · READ before WRITE)."""

from .adapter import ADAPTER_ID, RailwayAdapter
from .flags import (
    ENV_LIVE,
    ENV_PHASE,
    ENV_TOKEN,
    railway_live_enabled,
    railway_live_phase,
)
from .live_transport import LiveRailwayTransport
from .path import RailwayGatedResult, build_railway_transport, execute_railway_gated
from .transport import MockRailwayTransport, RailwayTransport, RailwayTransportResult

__all__ = [
    "ADAPTER_ID",
    "ENV_LIVE",
    "ENV_PHASE",
    "ENV_TOKEN",
    "LiveRailwayTransport",
    "MockRailwayTransport",
    "RailwayAdapter",
    "RailwayGatedResult",
    "RailwayTransport",
    "RailwayTransportResult",
    "build_railway_transport",
    "execute_railway_gated",
    "railway_live_enabled",
    "railway_live_phase",
]
