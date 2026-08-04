"""Conversation Memory — current session only (≠ Workspace · ≠ Core)."""

from .provider import ConversationMemoryProvider
from .store import (
    ConversationMemory,
    get_conversation_memory,
    reset_conversation_memory_for_tests,
)
from .types import (
    ActiveWorkspaceContext,
    ConversationMemorySnapshot,
    ConversationTurn,
    OpenQuestion,
)

__all__ = [
    "ActiveWorkspaceContext",
    "ConversationMemory",
    "ConversationMemoryProvider",
    "ConversationMemorySnapshot",
    "ConversationTurn",
    "OpenQuestion",
    "get_conversation_memory",
    "reset_conversation_memory_for_tests",
]
