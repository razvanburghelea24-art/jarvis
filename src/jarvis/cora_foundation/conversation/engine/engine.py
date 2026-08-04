"""ConversationEngine — spine only (skeleton).

Flow (fixed order):
  submit(request)
    → validate()
    → build_context()
    → decide()
    → emit_state()
    → emit_response()

Produces later: ConversationEvents formalization · Streaming last
Never: Electron · React · Persona · Avatar · Camera · IPC · UI mutation

Logic lands piece-by-piece under Owner GO (Validator…ResponseBuilder done).
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    ConversationState,
)
from .context_builder import ContextBuilder
from .decision_engine import DecisionEngine
from .request_validator import RequestValidator
from .response_builder import ResponseBuilder
from .state_emitter import StateEmitter
from ._skeleton import SkeletonNotImplemented

# Re-export for callers / tests
__all__ = ["ConversationEngine", "SkeletonNotImplemented"]


class ConversationEngine:
    """
    Conversational motor spine.

    Components (none know Desktop/UI):
      RequestValidator · ContextBuilder · DecisionEngine ·
      ResponseBuilder · StateEmitter · ConversationEvents (via StateEmitter / events journal)
    """

    SKELETON = True
    """True until business logic is filled in component-by-component."""

    def __init__(
        self,
        *,
        validator: RequestValidator | None = None,
        context_builder: ContextBuilder | None = None,
        decision_engine: DecisionEngine | None = None,
        response_builder: ResponseBuilder | None = None,
        state_emitter: StateEmitter | None = None,
    ) -> None:
        self.validator = validator or RequestValidator()
        self.context_builder = context_builder or ContextBuilder()
        self.decision_engine = decision_engine or DecisionEngine()
        self.response_builder = response_builder or ResponseBuilder()
        self.state_emitter = state_emitter or StateEmitter()

    # ── named pipeline steps (extension points) ─────────────────────────

    def validate(self, request: Mapping[str, Any] | ConversationRequest) -> ConversationRequest:
        return self.validator.validate(request)

    def build_context(self, request: ConversationRequest) -> ConversationContext:
        return self.context_builder.build(request)

    def decide(
        self,
        request: ConversationRequest,
        context: ConversationContext,
    ) -> ConversationDecision:
        return self.decision_engine.decide(request, context)

    def emit_state(
        self,
        request: ConversationRequest,
        decision: ConversationDecision,
    ) -> ConversationState:
        """Publish ConversationState trail for decision; returns final state."""
        trail = self.state_emitter.emit_trail(decision, request)
        return trail[-1]

    def emit_response(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
    ) -> ConversationResponse:
        return self.response_builder.build(request, context, decision)

    # ── full spine ──────────────────────────────────────────────────────

    def submit(
        self,
        request: Mapping[str, Any] | ConversationRequest,
    ) -> ConversationResponse:
        """
        Canonical turn pipeline.

        Order is frozen:
          validate → build_context → decide → emit_state → emit_response
        Streaming is NOT part of this spine yet (comes last in Beta).
        """
        validated = self.validate(request)
        context = self.build_context(validated)
        decision = self.decide(validated, context)
        self.emit_state(validated, decision)
        return self.emit_response(validated, context, decision)
