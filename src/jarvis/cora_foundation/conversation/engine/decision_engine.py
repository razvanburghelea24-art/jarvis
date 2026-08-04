"""DecisionEngine — deterministic ConversationDecision (Beta v1).

Receives ConversationContext (+ Request). Produces ConversationDecision only.
Never calls Planner / Gateway / Tools / LLM / Memory / Electron / Persona.

May set planner_required=false|true in tool_intent metadata bag —
never executes Planner.
"""

from __future__ import annotations

from uuid import uuid4

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    DecisionKind,
)

SUPPORTED_CONTENT_KINDS = frozenset({"", "text", "chat", "command", "message"})

LABEL_ASK = "AskClarification"
LABEL_REVIEW = "NeedsReview"
LABEL_REFUSE = "Refuse"
LABEL_RESPOND = "Respond"


class DecisionEngine:
    """Rule-based decisions only. No side effects."""

    def decide(
        self,
        request: ConversationRequest,
        context: ConversationContext,
    ) -> ConversationDecision:
        label, kind, mode, confidence, reason = self._rule(request, context)
        meta = {
            "label": label,
            "decision": label,
            "confidence": confidence,
            "planner_required": False,
            "tool_required": False,
            "response_mode": mode,
            "metadata": {
                "rule": reason,
                "content_kind": self._content_kind(request),
                "context_workspace": context.workspace_id,
            },
        }
        return ConversationDecision(
            decision_id=f"dec_{uuid4().hex[:12]}",
            request_id=request.request_id,
            kind=kind,
            workspace_id=request.workspace_id,
            planner_ref=None,
            tool_intent=meta,
            reason=reason,
        )

    def _content_kind(self, request: ConversationRequest) -> str:
        raw = request.metadata.get("content_kind", request.metadata.get("kind", "text"))
        return str(raw or "text").strip().lower()

    def _attachments(self, request: ConversationRequest) -> list:
        att = request.metadata.get("attachments")
        if att is None:
            return []
        if isinstance(att, (list, tuple)):
            return list(att)
        return [att]

    def _rule(
        self,
        request: ConversationRequest,
        context: ConversationContext,
    ) -> tuple[str, DecisionKind, str, float, str]:
        text = (request.input or "").strip()
        attachments = self._attachments(request)
        content_kind = self._content_kind(request)

        # Unsupported kind → Refuse
        if content_kind not in SUPPORTED_CONTENT_KINDS:
            return (
                LABEL_REFUSE,
                DecisionKind.REFUSE,
                "refuse",
                0.99,
                f"unsupported content_kind={content_kind!r}",
            )

        # Attachment only (no text) → NeedsReview
        if not text and attachments:
            return (
                LABEL_REVIEW,
                DecisionKind.CLARIFY,
                "review",
                0.92,
                "attachment_only",
            )

        # Empty input → AskClarification
        if not text:
            return (
                LABEL_ASK,
                DecisionKind.CLARIFY,
                "clarification",
                0.95,
                "empty_input",
            )

        # Default → Respond
        confidence = min(0.95, 0.70 + min(len(text), 80) / 400.0)
        return (
            LABEL_RESPOND,
            DecisionKind.ANSWER,
            "direct",
            round(confidence, 4),
            "normal_input",
        )
