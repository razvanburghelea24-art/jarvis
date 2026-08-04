"""Conversation Engine — Core v1 modules.

HARD RULE:
  Conversation Engine produces only:
    ConversationResponse · ConversationState · ConversationEvents · Stream chunks
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
from .conversation_events import (
    CONTEXT_BUILT,
    CONVERSATION_COMPLETED,
    ConversationEvent,
    ConversationEvents,
    DECISION_MADE,
    EventJournal,
    PIPELINE_ORDER,
    REQUEST_ACCEPTED,
    REQUEST_VALIDATED,
    RESPONSE_BUILT,
    STATE_EMITTED,
    STREAM_CANCELLED,
    STREAM_CHUNK,
    STREAM_COMPLETED,
    STREAM_STARTED,
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
from .streaming import DEFAULT_CHUNK_SIZE, ResponseStreamer, StreamChunk, StreamResult

__all__ = [
    "CONTEXT_BUILT",
    "CONVERSATION_COMPLETED",
    "ConversationEngine",
    "ConversationEvent",
    "ConversationEvents",
    "ContextBuilder",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_LIMITS",
    "DECISION_MADE",
    "DecisionEngine",
    "ERROR_INVALID_JSON",
    "ERROR_INVALID_REQUEST",
    "ERROR_INVALID_TYPE",
    "ERROR_MISSING_FIELD",
    "ERROR_UNKNOWN_VERSION",
    "ERROR_WRONG_FAMILY",
    "ERROR_WRONG_KIND",
    "EventJournal",
    "PIPELINE_ORDER",
    "REQUEST_ACCEPTED",
    "REQUEST_VALIDATED",
    "RESPONSE_BUILT",
    "RequestValidationError",
    "RequestValidationResult",
    "RequestValidator",
    "ResponseBuilder",
    "ResponseStreamer",
    "STATE_EMITTED",
    "STREAM_CANCELLED",
    "STREAM_CHUNK",
    "STREAM_COMPLETED",
    "STREAM_STARTED",
    "SkeletonNotImplemented",
    "StateEmitter",
    "StreamChunk",
    "StreamResult",
    "StubConversationMemoryProvider",
    "StubCoreMemoryProvider",
    "StubRuntimeSnapshotProvider",
    "StubWorkspaceProvider",
]
