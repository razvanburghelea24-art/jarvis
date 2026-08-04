"""Live adapters — consume DispatchRequest only; produce AdapterResult.

Law: No Adapter without Dispatcher.
Does not modify Execution Layer (Planner / ToolRouter / Dispatcher).
"""

from .discord import DiscordAdapter, MockDiscordTransport
from .framework import FrameworkAdapter, MockFrameworkTransport
from .github import GitHubAdapter, MockGitHubTransport
from .railway import MockRailwayTransport, RailwayAdapter
from .result import AdapterResult, AdapterStatus

__all__ = [
    "AdapterResult",
    "AdapterStatus",
    "DiscordAdapter",
    "FrameworkAdapter",
    "GitHubAdapter",
    "MockDiscordTransport",
    "MockFrameworkTransport",
    "MockGitHubTransport",
    "MockRailwayTransport",
    "RailwayAdapter",
]
