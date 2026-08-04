"""ResponseBuilder — Decision + Context → ConversationResponse (Beta v1).

Deterministic templates only. Not an LLM wrapper.
No Planner · Gateway · Electron · Persona · Memory · State emit · Streaming.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
    LifecyclePhase,
)

# Decision label → (response_mode, text, actions, warnings)
_TEMPLATES: dict[str, tuple[str, str, tuple[dict[str, str], ...], tuple[str, ...]]] = {
    "Respond": (
        "placeholder",
        "[placeholder] A full answer will be produced in a later Beta stage.",
        (),
        (),
    ),
    "AskClarification": (
        "clarification",
        "I need a clearer request before I can continue. Please rephrase.",
        ({"type": "wait_owner", "reason": "clarification"},),
        (),
    ),
    "NeedsReview": (
        "review",
        "I received an attachment without text. Please confirm what you want me to do with it.",
        ({"type": "wait_owner", "reason": "review"},),
        ("attachment_without_text",),
    ),
    "Refuse": (
        "refuse",
        "I cannot process this content type.",
        (),
        ("unsupported_content",),
    ),
}

_KIND_FALLBACK: dict[str, str] = {
    "clarify": "AskClarification",
    "refuse": "Refuse",
    "answer": "Respond",
}


class ResponseBuilder:
    """Construct a contracts.v1 ConversationResponse from a decision."""

    def build(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
    ) -> ConversationResponse:
        label = self._label(decision)
        mode, text, actions, warnings = _TEMPLATES.get(
            label,
            _TEMPLATES["Respond"],
        )
        intent = dict(decision.tool_intent)
        meta: dict[str, Any] = {
            "label": label,
            "response_mode": mode,
            "actions": [dict(a) for a in actions],
            "warnings": list(warnings),
            "tool_intent": intent,
            "builder": "ResponseBuilder.v1",
            "context_workspace": context.workspace_id,
            "decision_kind": decision.kind.value,
            "decision_reason": decision.reason,
        }
        return ConversationResponse(
            response_id=f"resp_{uuid4().hex[:12]}",
            request_id=request.request_id,
            decision_id=decision.decision_id,
            phase=LifecyclePhase.COMPLETED,
            text=text,
            incomplete=False,
            tool_summary=None,
            citations=(),
            metadata=meta,
        )

    def _label(self, decision: ConversationDecision) -> str:
        raw = decision.tool_intent.get("label") or decision.tool_intent.get("decision")
        if raw:
            return str(raw)
        return _KIND_FALLBACK.get(decision.kind.value, "Respond")
