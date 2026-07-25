"""Conversation context builder (bounded, non-executable)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from ..conversation import build_conversation
from ..conversation.redaction import redact_secrets
from .explanations import summarize_selection
from .filters import is_authority_related, redact_for_output
from .limits import RecallLimits
from .models import ContextBundle, RecallItem


def build_conversation_context(
    *,
    current_message: Mapping[str, Any] | str,
    recent_messages: Optional[List[Any]] = None,
    recall_bundle: Optional[ContextBundle] = None,
    project_snapshot: Optional[Dict[str, Any]] = None,
    limits: Optional[RecallLimits] = None,
) -> Dict[str, Any]:
    """Assemble a bounded ConversationContext dict for answer support."""
    lim = limits or RecallLimits()
    if isinstance(current_message, str):
        current = {"role": "user", "content": current_message}
    else:
        current = dict(current_message)

    raw_recent = list(recent_messages or [])[-lim.max_recent_turns :]
    turns: List[Dict[str, Any]] = []
    for item in raw_recent:
        if isinstance(item, Mapping):
            content = redact_for_output(str(item.get("content") or item.get("text") or ""))
            role = str(item.get("role") or "unknown")
        else:
            content = redact_for_output(str(item))
            role = "unknown"
        if not content.strip():
            continue
        if is_authority_related(content):
            turns.append(
                {
                    "role": role,
                    "content": "[AUTHORITY_RELATED_EXCLUDED]",
                    "excluded": True,
                    "reason": "authority_related",
                }
            )
            continue
        turns.append({"role": role, "content": content})

    cur_raw = str(current.get("content") or "")
    cur_content = redact_for_output(cur_raw)
    if is_authority_related(cur_raw):
        cur_content = "[AUTHORITY_RELATED_EXCLUDED]"

    bundle = recall_bundle
    items = list(bundle.items) if bundle else []
    return {
        "current_user_request": {
            "role": str(current.get("role") or "user"),
            "content": cur_content,
        },
        "recent_relevant_turns": turns,
        "selected_approved_memories": [i.to_dict() for i in items],
        "current_project_snapshot": dict(project_snapshot or {}) if project_snapshot else None,
        "relevant_preferences": [
            i.to_dict() for i in items if i.item_type == "preference"
        ],
        "decisions": [i.to_dict() for i in items if i.item_type == "decision"],
        "timeline": list(bundle.timeline_events) if bundle else [],
        "contradictions": list(bundle.contradictions) if bundle else [],
        "uncertainty": list(bundle.unknowns) if bundle else [],
        "exclusions": list(bundle.excluded_items) if bundle else [],
        "provenance_references": [i.provenance for i in items],
        "selection_explanation": (
            bundle.selection_explanation
            if bundle
            else summarize_selection([], [], False)
        ),
        "truncated": bool(bundle.truncated) if bundle else False,
        "execution_forbidden": True,
        "approval_tokens_excluded": True,
    }
