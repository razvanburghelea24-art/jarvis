"""Harness fakes for not-yet-implemented spine steps."""

from __future__ import annotations

from uuid import uuid4

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    LifecyclePhase,
)
from ..engine.context_builder import ContextBuilder
from ..engine.decision_engine import DecisionEngine
from ..engine.request_validator import RequestValidator
from ..engine.response_builder import ResponseBuilder
from ..engine.state_emitter import StateEmitter

FakeRequestValidator = RequestValidator
FakeContextBuilder = ContextBuilder
FakeDecisionEngine = DecisionEngine
FakeStateEmitter = StateEmitter


class FakeResponseBuilder(ResponseBuilder):
    def build(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
    ) -> ConversationResponse:
        return ConversationResponse(
            response_id=f"resp_harness_{uuid4().hex[:8]}",
            request_id=request.request_id,
            decision_id=decision.decision_id,
            phase=LifecyclePhase.COMPLETED,
            text="",
            incomplete=False,
            citations=(),
            metadata={"harness": True},
        )
