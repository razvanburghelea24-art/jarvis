"""Validated conversation models for Brain V3 Phase 2."""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MESSAGE_ROLES = frozenset({"user", "assistant", "system", "tool", "unknown"})


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:16]}"


def new_conversation_id() -> str:
    return f"conv_{uuid.uuid4().hex[:16]}"


def normalize_role(role: Any) -> str:
    value = str(role or "unknown").strip().lower()
    return value if value in MESSAGE_ROLES else "unknown"


@dataclass
class Message:
    message_id: str
    conversation_id: str
    role: str
    content: str
    sequence_index: int
    content_hash: str
    author: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "author": self.author,
            "content": self.content,
            "timestamp": self.timestamp,
            "sequence_index": self.sequence_index,
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
        }


@dataclass
class Conversation:
    conversation_id: str
    messages: List[Message]
    source_type: str = "conversation"
    title: str = ""
    started_at: str = ""
    ended_at: str = ""
    participants: List[str] = field(default_factory=list)
    source_reference: str = ""
    content_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "source_type": self.source_type,
            "title": self.title,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "participants": list(self.participants),
            "messages": [m.to_dict() for m in self.messages],
            "source_reference": self.source_reference,
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
        }


def build_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    sequence_index: int,
    message_id: Optional[str] = None,
    author: str = "",
    timestamp: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    normalized = unicodedata.normalize("NFC", str(content or ""))
    return Message(
        message_id=message_id or new_message_id(),
        conversation_id=conversation_id,
        role=normalize_role(role),
        content=normalized,
        sequence_index=sequence_index,
        content_hash=compute_content_hash(normalized),
        author=str(author or "").strip(),
        timestamp=str(timestamp or "").strip(),
        metadata=dict(metadata or {}),
    )


def compute_conversation_hash(messages: List[Message]) -> str:
    parts = [f"{m.sequence_index}:{m.role}:{m.content_hash}" for m in messages]
    return compute_content_hash("\n".join(parts))
