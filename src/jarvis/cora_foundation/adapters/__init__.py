"""Live adapters — consume DispatchRequest only; produce AdapterResult.

Law: No Adapter without Dispatcher.
Does not modify Execution Layer (Planner / ToolRouter / Dispatcher).
"""

from .discord import (
    DiscordAdapter,
    LiveDiscordTransport,
    MockDiscordTransport,
    execute_discord_gated,
)
from .framework import (
    FrameworkAdapter,
    LiveFrameworkTransport,
    MockFrameworkTransport,
    execute_framework_gated,
)
from .github import (
    GitHubAdapter,
    LiveGitHubTransport,
    MockGitHubTransport,
    execute_github_gated,
)
from .n8n import MockN8NTransport, N8NAdapter
from .railway import (
    LiveRailwayTransport,
    MockRailwayTransport,
    RailwayAdapter,
    execute_railway_gated,
)
from .result import AdapterResult, AdapterStatus

__all__ = [
    "AdapterResult",
    "AdapterStatus",
    "DiscordAdapter",
    "FrameworkAdapter",
    "GitHubAdapter",
    "LiveDiscordTransport",
    "LiveFrameworkTransport",
    "LiveGitHubTransport",
    "LiveRailwayTransport",
    "MockDiscordTransport",
    "MockFrameworkTransport",
    "MockGitHubTransport",
    "MockN8NTransport",
    "MockRailwayTransport",
    "N8NAdapter",
    "RailwayAdapter",
    "execute_discord_gated",
    "execute_framework_gated",
    "execute_github_gated",
    "execute_railway_gated",
]
