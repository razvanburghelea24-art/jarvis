"""Conversation package public API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .context import SpeakerAttribution
from .models import (
    Conversation,
    Message,
    build_message,
    compute_conversation_hash,
    new_conversation_id,
    normalize_role,
)
from .normalizer import normalize_whitespace
from .segmentation import (
    dedupe_messages,
    detect_correction,
    detect_negation,
    detect_quoted_segments,
    order_messages,
)
from .validation import ConversationLimits, validate_conversation, validate_raw_messages


def build_conversation(
    raw: Dict[str, Any],
    *,
    limits: Optional[ConversationLimits] = None,
) -> Conversation:
    """Build a validated, ordered, deduplicated conversation from a raw dict."""
    lim = limits or ConversationLimits()
    raw_messages = raw.get("messages") or []
    if not isinstance(raw_messages, list):
        from ..errors import ValidationError

        raise ValidationError("messages must be a list")

    validate_raw_messages(raw_messages, limits=lim)

    conversation_id = str(raw.get("conversation_id") or new_conversation_id())
    messages: List[Message] = []
    for index, item in enumerate(raw_messages):
        if not isinstance(item, dict):
            continue
        content = normalize_whitespace(str(item.get("content") or ""))
        if not content:
            continue
        messages.append(
            build_message(
                conversation_id=conversation_id,
                role=str(item.get("role") or "unknown"),
                content=content,
                sequence_index=int(item.get("sequence_index", index)),
                message_id=str(item.get("message_id") or ""),
                author=str(item.get("author") or ""),
                timestamp=str(item.get("timestamp") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
        )

    messages = order_messages(dedupe_messages(messages))
    conversation = Conversation(
        conversation_id=conversation_id,
        source_type=str(raw.get("source_type") or "conversation"),
        title=str(raw.get("title") or ""),
        started_at=str(raw.get("started_at") or ""),
        ended_at=str(raw.get("ended_at") or ""),
        participants=[str(p) for p in (raw.get("participants") or [])],
        messages=messages,
        source_reference=str(raw.get("source_reference") or ""),
        content_hash="",
        metadata=dict(raw.get("metadata") or {}),
    )
    conversation.content_hash = compute_conversation_hash(conversation.messages)
    validate_conversation(conversation, limits=lim)
    return conversation


__all__ = [
    "Conversation",
    "Message",
    "SpeakerAttribution",
    "ConversationLimits",
    "build_conversation",
    "normalize_whitespace",
    "detect_quoted_segments",
    "detect_negation",
    "detect_correction",
    "order_messages",
    "dedupe_messages",
]
