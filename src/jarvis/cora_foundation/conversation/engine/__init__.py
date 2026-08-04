"""Conversation Engine Skeleton — structure only, no business logic.

HARD RULE:
  Conversation Engine produces only:
    ConversationResponse · ConversationState · ConversationEvents
  It does NOT send IPC, change UI, or talk to Electron / React / Persona / Avatar / Camera.
"""

from .context_builder import ContextBuilder
from .context_providers import (
    DEFAULT_LIMITS,
    StubConversationMemoryProvider,
    StubCoreMemoryProvider,
    StubRuntimeSnapshotProvider,
    StubWorkspaceProvider,
)
from .decision_engine import DecisionEngine
from .engine import ConversationEngine, SkeletonNotImplemented
from .request_validator import (
    ERROR_INVALID_JSON,
    ERROR_INVALID_REQUEST,
    ERROR_INVALID_TYPE,
    ERROR_MISSING_FIELD,
    ERROR_UNKNOWN_VERSION,
    ERROR_WRONG_FAMILY,
    ERROR_WRONG_KIND,
    RequestValidationError,
    RequestValidationResult,
    RequestValidator,
)
from .response_builder import ResponseBuilder
from .state_emitter import StateEmitter

__all__ = [
    "ConversationEngine",
    "ContextBuilder",
    "DEFAULT_LIMITS",
    "DecisionEngine",
    "ERROR_INVALID_JSON",
    "ERROR_INVALID_REQUEST",
    "ERROR_INVALID_TYPE",
    "ERROR_MISSING_FIELD",
    "ERROR_UNKNOWN_VERSION",
    "ERROR_WRONG_FAMILY",
    "ERROR_WRONG_KIND",
    "RequestValidationError",
    "RequestValidationResult",
    "RequestValidator",
    "ResponseBuilder",
    "SkeletonNotImplemented",
    "StateEmitter",
    "StubConversationMemoryProvider",
    "StubCoreMemoryProvider",
    "StubRuntimeSnapshotProvider",
    "StubWorkspaceProvider",
]
