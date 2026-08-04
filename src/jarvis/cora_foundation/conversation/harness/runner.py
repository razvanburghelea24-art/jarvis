"""ConversationHarness — run contract-communication scenarios without Desktop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...gateway.audit_hooks import AuditJournal
from ...gateway.conversation_accept import ConversationAcceptResult, accept_conversation_request
from ..contracts import ConversationRequest, ConversationResponse, ConversationState
from ..engine import (
    ConversationEngine,
    ContextBuilder,
    ConversationEvents,
    DecisionEngine,
    EventJournal,
    RequestValidator,
    ResponseBuilder,
    ResponseStreamer,
    StateEmitter,
    StreamResult,
)
from ..events import EVENT_CONVERSATION_STATE_CHANGED, get_conversation_event_journal


@dataclass
class HarnessResult:
    ok: bool
    gateway: ConversationAcceptResult | None = None
    response: ConversationResponse | None = None
    states: list[ConversationState] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    conversation_events: list[dict[str, Any]] = field(default_factory=list)
    stream: StreamResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "gateway": self.gateway.to_dict() if self.gateway else None,
            "response": self.response.to_canonical_dict() if self.response else None,
            "states": [s.to_canonical_dict() for s in self.states],
            "errors": list(self.errors),
            "conversation_events": list(self.conversation_events),
            "stream": self.stream.to_dict() if self.stream else None,
            "events": get_conversation_event_journal().to_timeline(limit=40),
        }


class ConversationHarness:
    """Gateway Accept → Engine → optional Streaming. Journals via observers."""

    def __init__(self, *, audit: AuditJournal | None = None, chunk_size: int = 8) -> None:
        self.audit = audit or AuditJournal()
        self.event_journal = EventJournal()

        def _on_conversation_event(event) -> None:
            self.event_journal.record(event)

        def _on_state(state: ConversationState) -> None:
            get_conversation_event_journal().record_state(
                presentation=state.presentation.value,
                request_id=state.request_id,
                workspace_id=state.workspace_id,
                session_id=state.session_id,
                lifecycle=state.lifecycle.value,
            )

        self.conversation_events = ConversationEvents(on_event=_on_conversation_event)
        self.emitter = StateEmitter(on_state=_on_state)
        self.streamer = ResponseStreamer(
            events=self.conversation_events,
            state_emitter=self.emitter,
            chunk_size=chunk_size,
        )
        self.engine = ConversationEngine(
            validator=RequestValidator(),
            context_builder=ContextBuilder(),
            decision_engine=DecisionEngine(),
            response_builder=ResponseBuilder(),
            state_emitter=self.emitter,
            conversation_events=self.conversation_events,
            streamer=self.streamer,
        )

    def accept(self, payload: Mapping[str, Any] | ConversationRequest | None) -> ConversationAcceptResult:
        result = accept_conversation_request(payload, audit=self.audit)
        if result.ok and result.request is not None:
            self.conversation_events.request_accepted(
                result.request,
                code=result.code,
                status_code=result.status_code,
            )
        return result

    def emit_state_sequence(
        self,
        request: ConversationRequest,
        presentations: list[str],
    ) -> list[ConversationState]:
        out: list[ConversationState] = []
        previous: str | None = None
        for p in presentations:
            out.append(
                self.emitter.emit_transition(request, previous=previous, current=p)
            )
            previous = p
        return out

    def run_turn(self, payload: Mapping[str, Any], *, stream: bool = False) -> HarnessResult:
        gateway = self.accept(payload)
        if not gateway.ok or gateway.request is None:
            return HarnessResult(
                ok=False,
                gateway=gateway,
                errors=list(gateway.errors) or [gateway.message],
                conversation_events=self.event_journal.to_list(),
            )

        request = gateway.request
        states = self.emit_state_sequence(request, ["Idle", "Listening"])
        try:
            response = self.engine.submit(request)
            stream_result = None
            if stream:
                stream_result = self.engine.stream_run(response, request)
        except Exception as exc:  # noqa: BLE001
            return HarnessResult(
                ok=False,
                gateway=gateway,
                states=states,
                errors=[str(exc)],
                conversation_events=self.event_journal.to_list(),
            )

        return HarnessResult(
            ok=True,
            gateway=gateway,
            response=response,
            states=states,
            conversation_events=self.event_journal.to_list(),
            stream=stream_result,
        )

    def timeline_has_state_changed(self, *, current_state: str | None = None) -> bool:
        events = get_conversation_event_journal().events()
        changed = [e for e in events if e.event_type == EVENT_CONVERSATION_STATE_CHANGED]
        if not changed:
            return False
        if current_state is None:
            return True
        return any(e.current_state == current_state for e in changed)
