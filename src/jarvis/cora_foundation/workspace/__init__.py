"""cora_foundation.workspace — Workspace Engine (identity context, not LLM)."""

from .context import ActiveWorkspaceContext
from .engine import WorkspaceEngine, WorkspaceEngineProvider
from .providers import InMemoryWorkspaceStore, StubWorkspaceStore, WorkspaceStore

__all__ = [
    "ActiveWorkspaceContext",
    "InMemoryWorkspaceStore",
    "StubWorkspaceStore",
    "WorkspaceEngine",
    "WorkspaceEngineProvider",
    "WorkspaceStore",
]
