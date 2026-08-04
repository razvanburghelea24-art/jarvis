"""Live adapters — consume DispatchRequest only; produce AdapterResult.

Law: No Adapter without Dispatcher.
Does not modify Execution Layer (Planner / ToolRouter / Dispatcher).
"""

from .discord import DiscordAdapter, MockDiscordTransport
from .github import GitHubAdapter, MockGitHubTransport
from .result import AdapterResult, AdapterStatus

__all__ = [
    "AdapterResult",
    "AdapterStatus",
    "DiscordAdapter",
    "GitHubAdapter",
    "MockDiscordTransport",
    "MockGitHubTransport",
]
