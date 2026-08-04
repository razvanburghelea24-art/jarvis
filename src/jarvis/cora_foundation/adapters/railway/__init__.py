"""Railway Adapter — DispatchRequest → AdapterResult (mock transport default)."""

from .adapter import ADAPTER_ID, RailwayAdapter
from .transport import MockRailwayTransport, RailwayTransport, RailwayTransportResult

__all__ = [
    "ADAPTER_ID",
    "MockRailwayTransport",
    "RailwayAdapter",
    "RailwayTransport",
    "RailwayTransportResult",
]
