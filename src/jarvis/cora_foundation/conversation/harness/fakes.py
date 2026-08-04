"""Harness-only fakes — contract-shaped stubs, zero product intelligence."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    ConversationState,
    DecisionKind,
    LifecyclePhase,
    PresentationHint,
    validate_request,
)
from ..engine.context_builder import ContextBuilder
from ..engine.decision_engine import DecisionEngine
from ..engine.request_validator import RequestValidator
from ..engine.response_builder import ResponseBuilder
from ..engine.state_emitter import StateEmitter
from ..events import get_conversation_event_journal


class FakeRequestValidator(RequestValidator):
    """Uses real schema validation — proves contracts speak to the spine."""

    def validate(self, request: Mapping[str, Any] | ConversationRequest) -> ConversationRequest:
        if isinstance(request, ConversationRequest):
            raw = request.to_canonical_dict()
        else:
            raw = dict(request)
            if "schema_family" not in raw:
                raw = {
                    "schema_family": "cora.conversation.contracts",
                    "schema_version": 1,
                    "kind": "ConversationRequest",
                    **raw,
                }
        return validate_request(raw)


class FakeContextBuilder(ContextBuilder):
    def build(self, request: ConversationRequest) -> ConversationContext:
        return ConversationContext(
            request_id=request.request_id,
            session_id=request.session_id,
            workspace_id=request.workspace_id,
            conversation={"turns": 0, "harness": True},
            workspace={"id": request.workspace_id},
            core={"harness": True},
            runtime={"e_stop": False},
            sealed=True,
        )


class FakeDecisionEngine(DecisionEngine):
    def decide(
        self,
        request: ConversationRequest,
        context: ConversationContext,
    ) -> ConversationDecision:
        return ConversationDecision(
            decision_id=f"dec_harness_{uuid4().hex[:8]}",
            request_id=request.request_id,
            kind=DecisionKind.ANSWER,
            workspace_id=request.workspace_id,
            planner_ref=None,
            tool_intent={},
            reason="harness-fake-answer",
        )


class FakeResponseBuilder(ResponseBuilder):
    """Empty ConversationResponse — DoD Test 4."""

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


class FakeStateEmitter(StateEmitter):
    """Emits ConversationState + ConversationStateChanged (no Desktop)."""

    def emit(
        self,
        request: ConversationRequest,
        *,
        presentation: str,
        lifecycle: str | None = None,
    ) -> ConversationState:
        life = lifecycle or (
            "Listening"
            if presentation == "Listening"
            else "Idle"
            if presentation == "Idle"
            else "Thinking"
        )
        state = ConversationState(
            session_id=request.session_id,
            request_id=request.request_id,
            workspace_id=request.workspace_id,
            lifecycle=LifecyclePhase(life),
            presentation=PresentationHint(presentation),
        )
        get_conversation_event_journal().record_state(
            presentation=state.presentation.value,
            request_id=state.request_id,
            workspace_id=state.workspace_id,
            session_id=state.session_id,
            lifecycle=state.lifecycle.value,
        )
        return state
