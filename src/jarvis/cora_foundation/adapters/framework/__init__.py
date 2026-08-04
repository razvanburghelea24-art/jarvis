"""Framework Adapter — DispatchRequest → AdapterResult (mock transport default)."""

from .adapter import ADAPTER_ID, FrameworkAdapter
from .transport import FrameworkTransport, FrameworkTransportResult, MockFrameworkTransport

__all__ = [
    "ADAPTER_ID",
    "FrameworkAdapter",
    "FrameworkTransport",
    "FrameworkTransportResult",
    "MockFrameworkTransport",
]
