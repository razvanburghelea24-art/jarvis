"""GitHub Adapter — DispatchRequest → AdapterResult (mock default · LIVE optional)."""

from .adapter import ADAPTER_ID, GitHubAdapter
from .flags import (
    ENV_LIVE,
    ENV_PHASE,
    ENV_TOKEN,
    github_live_enabled,
    github_live_phase,
)
from .live_transport import LiveGitHubTransport
from .path import GitHubGatedResult, build_github_transport, execute_github_gated
from .transport import GitHubTransport, GitHubTransportResult, MockGitHubTransport

__all__ = [
    "ADAPTER_ID",
    "ENV_LIVE",
    "ENV_PHASE",
    "ENV_TOKEN",
    "GitHubAdapter",
    "GitHubGatedResult",
    "GitHubTransport",
    "GitHubTransportResult",
    "LiveGitHubTransport",
    "MockGitHubTransport",
    "build_github_transport",
    "execute_github_gated",
    "github_live_enabled",
    "github_live_phase",
]
