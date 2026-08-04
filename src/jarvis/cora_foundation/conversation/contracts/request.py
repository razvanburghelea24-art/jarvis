"""ConversationRequest — immutable user turn input (v1 frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .schema import KIND_REQUEST, envelope, freeze_mapping


@dataclass(frozen=True)
class ConversationRequest:
    request_id: str
    session_id: str
    workspace_id: str
    input: str
    barge_in: bool = False
    resume_of: str | None = None
    client_at: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_canonical_dict(self) -> dict[str, Any]:
        return envelope(
            kind=KIND_REQUEST,
            payload={
                "request_id": self.request_id,
                "session_id": self.session_id,
                "workspace_id": self.workspace_id,
                "input": self.input,
                "barge_in": self.barge_in,
                "resume_of": self.resume_of,
                "client_at": self.client_at,
                "metadata": dict(self.metadata),
            },
        )
