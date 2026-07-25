"""Conversation bounds validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..errors import LimitExceededError, ValidationError
from .models import Conversation, Message, normalize_role


@dataclass(frozen=True)
class ConversationLimits:
    max_messages: int = 1_000
    max_message_length: int = 8_000
    max_title_length: int = 256
    max_participants: int = 64


def validate_message(
    message: Message,
    *,
    limits: Optional[ConversationLimits] = None,
) -> None:
    lim = limits or ConversationLimits()
    if not message.message_id:
        raise ValidationError("message_id required")
    if not message.conversation_id:
        raise ValidationError("conversation_id required")
    if normalize_role(message.role) not in {
        "user",
        "assistant",
        "system",
        "tool",
        "unknown",
    }:
        raise ValidationError("invalid message role")
    if len(message.content) > lim.max_message_length:
        raise LimitExceededError("message content exceeds max length")
    if message.sequence_index < 0:
        raise ValidationError("sequence_index must be non-negative")


def validate_conversation(
    conversation: Conversation,
    *,
    limits: Optional[ConversationLimits] = None,
) -> None:
    lim = limits or ConversationLimits()
    if not conversation.conversation_id:
        raise ValidationError("conversation_id required")
    if len(conversation.title) > lim.max_title_length:
        raise LimitExceededError("conversation title exceeds max length")
    if len(conversation.participants) > lim.max_participants:
        raise LimitExceededError("too many participants")
    if len(conversation.messages) > lim.max_messages:
        raise LimitExceededError("conversation exceeds max messages")
    for message in conversation.messages:
        validate_message(message, limits=lim)


def validate_raw_messages(
    messages: Iterable[dict],
    *,
    limits: Optional[ConversationLimits] = None,
) -> None:
    lim = limits or ConversationLimits()
    count = 0
    for raw in messages:
        count += 1
        if count > lim.max_messages:
            raise LimitExceededError("conversation exceeds max messages")
        content = str(raw.get("content") or "")
        if len(content) > lim.max_message_length:
            raise LimitExceededError("message content exceeds max length")
