"""Conversation package — contracts only in Beta 1.0 Schema Freeze.

No Engine, Planner wiring, Gateway handlers, Desktop, Persona, or Avatar here.
"""

from .contracts import (
    SCHEMA_FAMILY,
    SCHEMA_VERSION,
    SCHEMA_ID,
    ConversationRequest,
    ConversationContext,
    ConversationDecision,
    ConversationResponse,
    ConversationState,
    DecisionKind,
    LifecyclePhase,
    PresentationHint,
    ErrorClass,
    ValidationError,
    validate,
    validate_request,
    validate_context,
    validate_decision,
    validate_response,
    validate_state,
    to_canonical_json,
    from_canonical_json,
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
