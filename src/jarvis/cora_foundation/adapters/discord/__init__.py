"""Discord Adapter — mock default · LIVE optional."""

from .adapter import ADAPTER_ID, DiscordAdapter
from .flags import ENV_LIVE, ENV_PHASE, ENV_TOKEN, discord_live_enabled, discord_live_phase
from .live_transport import LiveDiscordTransport
from .path import DiscordGatedResult, build_discord_transport, execute_discord_gated
from .transport import DiscordTransport, DiscordTransportResult, MockDiscordTransport

__all__ = [
    "ADAPTER_ID",
    "ENV_LIVE",
    "ENV_PHASE",
    "ENV_TOKEN",
    "DiscordAdapter",
    "DiscordGatedResult",
    "DiscordTransport",
    "DiscordTransportResult",
    "LiveDiscordTransport",
    "MockDiscordTransport",
    "build_discord_transport",
    "discord_live_enabled",
    "discord_live_phase",
    "execute_discord_gated",
]
