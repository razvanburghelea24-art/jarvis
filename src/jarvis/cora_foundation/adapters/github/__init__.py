"""GitHub Adapter — DispatchRequest → AdapterResult (mock default · LIVE optional)."""

from .acceptance import AcceptanceReport, run_acceptance_suite
from .adapter import ADAPTER_ID, GitHubAdapter
from .flags import (
    ENV_LIVE,
    ENV_PHASE,
    ENV_TOKEN,
    github_live_enabled,
    github_live_phase,
)
from .live_transport import LiveGitHubTransport
from .metrics import ChainMetrics
from .path import GitHubGatedResult, build_github_transport, execute_github_gated
from .transport import GitHubTransport, GitHubTransportResult, MockGitHubTransport

__all__ = [
    "ADAPTER_ID",
    "AcceptanceReport",
    "ChainMetrics",
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
    "run_acceptance_suite",
]
