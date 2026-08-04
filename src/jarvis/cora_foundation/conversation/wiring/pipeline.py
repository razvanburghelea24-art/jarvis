"""Router Wiring — official Beta Foundation pipeline (integration only).

Connects existing modules. Does not add Planner/Tools/UI/new provider logic.
Does not modify Conversation Engine Core v1 · LLMAdapter · Workspace Engine internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...llm import (
    LLMRequest,
    LLMResponse,
    ModelRouter,
    RouteDecision,
    RouteNeeds,
    build_llm_request,
    routing_test_registry,
)
from ...llm.from_context import DEFAULT_SYSTEM
from ...planner import PlannerDecision, PlannerRouter
from ...workspace import WorkspaceEngine, WorkspaceEngineProvider
from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    LifecyclePhase,
    ValidationError,
)
from ..engine import (
    ContextBuilder,
    ConversationEngine,
    ConversationEvents,
    DecisionEngine,
    EventJournal,
    RequestValidationError,
    RequestValidator,
    ResponseBuilder,
    ResponseStreamer,
    StateEmitter,
)
from ..engine.streaming import StreamResult
from ..memory import (
    ConversationMemory,
    ConversationMemoryProvider,
    get_conversation_memory,
)
from .needs import route_needs_from_context


@dataclass
class WiredTurnResult:
    ok: bool
    request: ConversationRequest | None = None
    context: ConversationContext | None = None
    decision: ConversationDecision | None = None
    planner: PlannerDecision | None = None
    route: RouteDecision | None = None
    llm: LLMResponse | None = None
    response: ConversationResponse | None = None
    stream: StreamResult | None = None
    errors: list[str] = field(default_factory=list)
    conversation_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "request_id": self.request.request_id if self.request else None,
            "workspace_id": self.context.workspace_id if self.context else None,
            "decision_label": (
                dict(self.decision.tool_intent).get("label") if self.decision else None
            ),
            "planner": self.planner.to_canonical_dict() if self.planner else None,
            "route": self.route.to_dict() if self.route else None,
            "llm_provider": self.llm.provider if self.llm else None,
            "response": self.response.to_canonical_dict() if self.response else None,
            "stream": self.stream.to_dict() if self.stream else None,
            "errors": list(self.errors),
            "conversation_events": list(self.conversation_events),
        }


class WiredConversationPipeline:
    """
    Official chain:

      validate → memory → workspace → context → decide
        → (Respond? router → llm) → response → state → events → stream

    SSOT for Beta Foundation (with LLM). Core v1 without LLM remains
    ConversationEngine.submit / Harness — intentional dual path, not a bypass.
    """

    PIPELINE_ID = "cora.beta.foundation.wired.v1"

    def __init__(
        self,
        *,
        memory: ConversationMemory | None = None,
        workspace: WorkspaceEngine | None = None,
        router: ModelRouter | None = None,
        validator: RequestValidator | None = None,
        decision_engine: DecisionEngine | None = None,
        response_builder: ResponseBuilder | None = None,
        events: ConversationEvents | None = None,
        event_journal: EventJournal | None = None,
        planner_router: PlannerRouter | None = None,
        chunk_size: int = 24,
    ) -> None:
        self.memory = memory or get_conversation_memory()
        self.workspace = workspace or WorkspaceEngine()
        self.router = router or ModelRouter(routing_test_registry())
        self.validator = validator or RequestValidator()
        self.decision_engine = decision_engine or DecisionEngine()
        self.response_builder = response_builder or ResponseBuilder()
        self.planner_router = planner_router or PlannerRouter()
        self.event_journal = event_journal or EventJournal()

        def _on_event(event) -> None:
            self.event_journal.record(event)

        self.events = events or ConversationEvents(on_event=_on_event)
        self.state_emitter = StateEmitter()
        self.streamer = ResponseStreamer(
            events=self.events,
            state_emitter=self.state_emitter,
            chunk_size=chunk_size,
        )
        self.context_builder = ContextBuilder(
            conversation_memory=ConversationMemoryProvider(self.memory),
            workspace=WorkspaceEngineProvider(self.workspace),
        )
        # Core engine kept for contracts / streaming helpers — submit path not used as SSOT
        self.engine = ConversationEngine(
            validator=self.validator,
            context_builder=self.context_builder,
            decision_engine=self.decision_engine,
            response_builder=self.response_builder,
            state_emitter=self.state_emitter,
            conversation_events=self.events,
            streamer=self.streamer,
        )

    def run(
        self,
        payload: Mapping[str, Any] | ConversationRequest,
        *,
        stream: bool = True,
        needs_override: RouteNeeds | Mapping[str, Any] | None = None,
    ) -> WiredTurnResult:
        try:
            request = self.validator.validate(payload)
        except (RequestValidationError, ValidationError, ValueError) as exc:
            return WiredTurnResult(ok=False, errors=[str(exc)])

        self.events.request_validated(request)

        # Conversation Memory + Workspace (identity) before ContextBuilder
        self.workspace.ensure_active(request.session_id, request.workspace_id)
        self.memory.bind_workspace(request.session_id, request.workspace_id)
        self.memory.append_user(
            request.session_id,
            request.input or "",
            request_id=request.request_id,
            workspace_id=request.workspace_id,
        )

        context = self.context_builder.build(request)
        self.events.context_built(request, workspace_id=context.workspace_id)

        decision = self.decision_engine.decide(request, context)
        label = str(decision.tool_intent.get("label") or decision.kind.value)
        self.events.decision_made(
            request,
            decision_id=decision.decision_id,
            kind=decision.kind.value,
            label=label,
            reason=decision.reason,
        )

        planner = self.planner_router.route(
            request, context, decision, workspace=self.workspace
        )

        route: RouteDecision | None = None
        llm: LLMResponse | None = None
        if label == "Respond":
            needs = needs_override or route_needs_from_context(context, self.workspace)
            route = self.router.resolve(needs)
            llm_req = build_llm_request(
                request,
                context,
                system_prompt=DEFAULT_SYSTEM,
                model=route.model_id,
                metadata={
                    "pipeline": self.PIPELINE_ID,
                    "routed_provider": route.provider_id,
                    "route_reason": route.reason,
                    "planner_required": planner.required,
                    "planner_route": planner.route.value,
                },
            )
            adapter = self.router.registry.get(route.provider_id).adapter
            llm = adapter.complete(llm_req)

        final_state = self.state_emitter.emit_trail(decision, request)[-1]
        self.events.state_emitted(
            request,
            presentation=final_state.presentation.value,
            lifecycle=final_state.lifecycle.value,
        )

        response = self._build_response(request, context, decision, llm=llm, route=route)
        self.events.response_built(
            request,
            response_id=response.response_id,
            response_mode=str(response.metadata.get("response_mode") or ""),
            label=label,
        )

        self.memory.append_assistant(
            request.session_id,
            response.text,
            request_id=request.request_id,
            response_id=response.response_id,
        )
        if label in {"AskClarification", "NeedsReview"}:
            self.memory.add_open_question(
                request.session_id,
                response.text,
                kind="clarification" if label == "AskClarification" else "review",
                request_id=request.request_id,
            )

        stream_result = None
        if stream:
            stream_result = self.streamer.run(response, request)

        self.events.conversation_completed(
            request,
            response_id=response.response_id,
            decision_id=decision.decision_id,
            presentation=final_state.presentation.value,
            routed_provider=(route.provider_id if route else None),
        )

        return WiredTurnResult(
            ok=True,
            request=request,
            context=context,
            decision=decision,
            planner=planner,
            route=route,
            llm=llm,
            response=response,
            stream=stream_result,
            conversation_events=self.event_journal.to_list(),
        )

    def _build_response(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
        *,
        llm: LLMResponse | None,
        route: RouteDecision | None,
    ) -> ConversationResponse:
        base = self.response_builder.build(request, context, decision)
        if llm is None:
            return base
        meta = dict(base.metadata)
        meta.update(
            {
                "response_mode": "llm",
                "builder": "ResponseBuilder.v1+wiring",
                "pipeline": self.PIPELINE_ID,
                "llm_provider": llm.provider,
                "llm_model": llm.model,
                "routed_provider": route.provider_id if route else None,
                "route_reason": route.reason if route else None,
                "llm_usage": dict(llm.usage),
            }
        )
        return ConversationResponse(
            response_id=base.response_id,
            request_id=base.request_id,
            decision_id=base.decision_id,
            phase=LifecyclePhase.COMPLETED,
            text=llm.text,
            incomplete=False,
            tool_summary=base.tool_summary,
            citations=base.citations,
            metadata=meta,
        )
