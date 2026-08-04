"""ConversationHarness — run contract-communication scenarios without Desktop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...gateway.audit_hooks import AuditJournal
from ...gateway.conversation_accept import ConversationAcceptResult, accept_conversation_request
from ..contracts import ConversationRequest, ConversationResponse, ConversationState
from ..engine import ConversationEngine, RequestValidator
from ..events import EVENT_CONVERSATION_STATE_CHANGED, get_conversation_event_journal
from .fakes import (
    FakeContextBuilder,
    FakeDecisionEngine,
    FakeResponseBuilder,
    FakeStateEmitter,
)


@dataclass
class HarnessResult:
    ok: bool
    gateway: ConversationAcceptResult | None = None
    response: ConversationResponse | None = None
    states: list[ConversationState] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "gateway": self.gateway.to_dict() if self.gateway else None,
            "response": self.response.to_canonical_dict() if self.response else None,
            "states": [s.to_canonical_dict() for s in self.states],
            "errors": list(self.errors),
            "events": get_conversation_event_journal().to_timeline(limit=40),
        }


class ConversationHarness:
    """
    Banc de test:
      ConversationRequest → Fake Gateway → Skeleton(fakes) → Fake Response

    No LLM / Planner / Memory / Tools / Streaming / Electron.
    """

    def __init__(self, *, audit: AuditJournal | None = None) -> None:
        self.audit = audit or AuditJournal()
        self.emitter = FakeStateEmitter()
        self.engine = ConversationEngine(
            validator=RequestValidator(),
            context_builder=FakeContextBuilder(),
            decision_engine=FakeDecisionEngine(),
            response_builder=FakeResponseBuilder(),
            state_emitter=self.emitter,
        )
        # Real RequestValidator; remaining spine steps still harness fakes.
        self.engine.SKELETON = True

    def accept(self, payload: Mapping[str, Any] | ConversationRequest | None) -> ConversationAcceptResult:
        """Fake Gateway Accept (validate-only)."""
        return accept_conversation_request(payload, audit=self.audit)

    def emit_state_sequence(
        self,
        request: ConversationRequest,
        presentations: list[str],
    ) -> list[ConversationState]:
        """Emit presentation trail (e.g. Idle → Listening) for timeline DoD."""
        out: list[ConversationState] = []
        for p in presentations:
            out.append(self.emitter.emit(request, presentation=p))
        return out

    def run_turn(self, payload: Mapping[str, Any]) -> HarnessResult:
        """
        Full harness turn:
          1) Gateway Accept
          2) Idle → Listening state trail
          3) Skeleton submit → empty ConversationResponse
        """
        gateway = self.accept(payload)
        if not gateway.ok or gateway.request is None:
            return HarnessResult(
                ok=False,
                gateway=gateway,
                errors=list(gateway.errors) or [gateway.message],
            )

        request = gateway.request
        states = self.emit_state_sequence(request, ["Idle", "Listening"])
        try:
            # submit also emits Thinking via spine — harness fakes allow it
            response = self.engine.submit(request)
        except Exception as exc:  # noqa: BLE001 — harness surfaces errors
            return HarnessResult(
                ok=False,
                gateway=gateway,
                states=states,
                errors=[str(exc)],
            )

        return HarnessResult(ok=True, gateway=gateway, response=response, states=states)

    def timeline_has_state_changed(self, *, current_state: str | None = None) -> bool:
        events = get_conversation_event_journal().events()
        changed = [e for e in events if e.event_type == EVENT_CONVERSATION_STATE_CHANGED]
        if not changed:
            return False
        if current_state is None:
            return True
        return any(e.current_state == current_state for e in changed)
