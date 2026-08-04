"""n8n Adapter — DispatchRequest → AdapterResult (mock transport default)."""

from .adapter import ADAPTER_ID, N8NAdapter
from .transport import MockN8NTransport, N8NTransport, N8NTransportResult

__all__ = [
    "ADAPTER_ID",
    "MockN8NTransport",
    "N8NAdapter",
    "N8NTransport",
    "N8NTransportResult",
]
