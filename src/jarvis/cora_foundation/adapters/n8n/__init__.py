"""n8n Adapter — mock default · LIVE optional (READ before EXECUTE)."""

from .adapter import ADAPTER_ID, N8NAdapter
from .flags import ENV_LIVE, ENV_PHASE, ENV_TOKEN, n8n_live_enabled, n8n_live_phase
from .live_transport import LiveN8NTransport
from .path import N8NGatedResult, build_n8n_transport, execute_n8n_gated
from .transport import MockN8NTransport, N8NTransport, N8NTransportResult

__all__ = [
    "ADAPTER_ID",
    "ENV_LIVE",
    "ENV_PHASE",
    "ENV_TOKEN",
    "LiveN8NTransport",
    "MockN8NTransport",
    "N8NAdapter",
    "N8NGatedResult",
    "N8NTransport",
    "N8NTransportResult",
    "build_n8n_transport",
    "execute_n8n_gated",
    "n8n_live_enabled",
    "n8n_live_phase",
]
