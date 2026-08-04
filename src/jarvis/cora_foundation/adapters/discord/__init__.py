"""Discord Adapter — DispatchRequest → AdapterResult (mock transport default)."""

from .adapter import ADAPTER_ID, DiscordAdapter
from .transport import DiscordTransport, DiscordTransportResult, MockDiscordTransport

__all__ = [
    "ADAPTER_ID",
    "DiscordAdapter",
    "DiscordTransport",
    "DiscordTransportResult",
    "MockDiscordTransport",
]
