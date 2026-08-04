"""Conversation Engine Skeleton — structure only, no business logic.

HARD RULE:
  Conversation Engine produces only:
    ConversationResponse · ConversationState · ConversationEvents
  It does NOT send IPC, change UI, or talk to Electron / React / Persona / Avatar / Camera.
"""

from .context_builder import ContextBuilder
from .decision_engine import DecisionEngine
from .engine import ConversationEngine, SkeletonNotImplemented
from .request_validator import RequestValidator
from .response_builder import ResponseBuilder
from .state_emitter import StateEmitter

__all__ = [
    "ConversationEngine",
    "ContextBuilder",
    "DecisionEngine",
    "RequestValidator",
    "ResponseBuilder",
    "SkeletonNotImplemented",
    "StateEmitter",
]
