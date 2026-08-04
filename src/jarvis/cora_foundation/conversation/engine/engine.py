"""ConversationEngine — conversational motor spine (Core v1).

Flow (fixed order):
  submit(request)
    → validate()
    → build_context()
    → decide()
    → emit_state()
    → emit_response()
    (+ ConversationEvents)
  stream(response, request)  ← optional progressive delivery (last)

Produces: ConversationResponse · ConversationState · ConversationEvents · Stream chunks
Never: Electron · React · Persona · Avatar · Camera · IPC · UI · Audit · LLM · Planner
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Mapping

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    ConversationState,
)
from .context_builder import ContextBuilder
from .conversation_events import ConversationEvents
from .decision_engine import DecisionEngine
from .request_validator import RequestValidator
from .response_builder import ResponseBuilder
from .state_emitter import StateEmitter
from .streaming import ResponseStreamer, StreamChunk, StreamResult
from ._skeleton import SkeletonNotImplemented

__all__ = ["ConversationEngine", "SkeletonNotImplemented"]


class ConversationEngine:
    """Conversational motor spine — Core v1 components, no Desktop knowledge."""

    SKELETON = False
    """False — Conversation Engine Core v1 structural modules are complete."""

    def __init__(
        self,
        *,
        validator: RequestValidator | None = None,
        context_builder: ContextBuilder | None = None,
        decision_engine: DecisionEngine | None = None,
        response_builder: ResponseBuilder | None = None,
        state_emitter: StateEmitter | None = None,
        conversation_events: ConversationEvents | None = None,
        streamer: ResponseStreamer | None = None,
    ) -> None:
        self.validator = validator or RequestValidator()
        self.context_builder = context_builder or ContextBuilder()
        self.decision_engine = decision_engine or DecisionEngine()
        self.response_builder = response_builder or ResponseBuilder()
        self.state_emitter = state_emitter or StateEmitter()
        self.conversation_events = conversation_events or ConversationEvents()
        self.streamer = streamer or ResponseStreamer(
            events=self.conversation_events,
            state_emitter=self.state_emitter,
        )

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
        trail = self.state_emitter.emit_trail(decision, request)
        return trail[-1]

    def emit_response(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
    ) -> ConversationResponse:
        return self.response_builder.build(request, context, decision)

    def stream(
        self,
        response: ConversationResponse,
        request: ConversationRequest,
    ) -> Iterator[StreamChunk]:
        """Deliver an already-built response as ordered chunks."""
        return self.streamer.stream(response, request)

    def stream_run(
        self,
        response: ConversationResponse,
        request: ConversationRequest,
    ) -> StreamResult:
        return self.streamer.run(response, request)

    def cancel_stream(self) -> None:
        self.streamer.cancel()

    def submit(
        self,
        request: Mapping[str, Any] | ConversationRequest,
    ) -> ConversationResponse:
        """
        Canonical turn pipeline (non-streaming).

        Order is frozen:
          validate → build_context → decide → emit_state → emit_response
        Use stream() / stream_run() after submit to deliver progressively.
        """
        ev = self.conversation_events
        validated = self.validate(request)
        ev.request_validated(validated)

        context = self.build_context(validated)
        ev.context_built(validated, workspace_id=context.workspace_id)

        decision = self.decide(validated, context)
        label = str(decision.tool_intent.get("label") or decision.kind.value)
        ev.decision_made(
            validated,
            decision_id=decision.decision_id,
            kind=decision.kind.value,
            label=label,
            reason=decision.reason,
        )

        final_state = self.emit_state(validated, decision)
        ev.state_emitted(
            validated,
            presentation=final_state.presentation.value,
            lifecycle=final_state.lifecycle.value,
        )

        response = self.emit_response(validated, context, decision)
        ev.response_built(
            validated,
            response_id=response.response_id,
            response_mode=str(response.metadata.get("response_mode") or ""),
            label=str(response.metadata.get("label") or label),
        )
        ev.conversation_completed(
            validated,
            response_id=response.response_id,
            decision_id=decision.decision_id,
            presentation=final_state.presentation.value,
        )
        return response
