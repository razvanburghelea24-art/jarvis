"""Conversation contracts v1 — types + validation only."""

from .context import ConversationContext
from .decision import ConversationDecision, DecisionKind
from .request import ConversationRequest
from .response import ConversationResponse
from .schema import SCHEMA_FAMILY, SCHEMA_ID, SCHEMA_VERSION
from .state import ConversationState, ErrorClass, LifecyclePhase, PresentationHint
from .validator import (
    ValidationError,
    from_canonical_json,
    to_canonical_json,
    validate,
    validate_context,
    validate_decision,
    validate_request,
    validate_response,
    validate_state,
)

__all__ = [
    "SCHEMA_FAMILY",
    "SCHEMA_VERSION",
    "SCHEMA_ID",
    "ConversationRequest",
    "ConversationContext",
    "ConversationDecision",
    "ConversationResponse",
    "ConversationState",
    "DecisionKind",
    "LifecyclePhase",
    "PresentationHint",
    "ErrorClass",
    "ValidationError",
    "validate",
    "validate_request",
    "validate_context",
    "validate_decision",
    "validate_response",
    "validate_state",
    "to_canonical_json",
    "from_canonical_json",
]
