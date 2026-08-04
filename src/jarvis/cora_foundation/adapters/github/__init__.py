"""GitHub Adapter — DispatchRequest → AdapterResult (mock transport default)."""

from .adapter import ADAPTER_ID, GitHubAdapter
from .transport import GitHubTransport, GitHubTransportResult, MockGitHubTransport

__all__ = [
    "ADAPTER_ID",
    "GitHubAdapter",
    "GitHubTransport",
    "GitHubTransportResult",
    "MockGitHubTransport",
]
