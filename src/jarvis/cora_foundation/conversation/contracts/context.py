"""ConversationContext — assembled prompt windows (v1 frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .schema import KIND_CONTEXT, envelope, freeze_mapping


@dataclass(frozen=True)
class ConversationContext:
    request_id: str
    session_id: str
    workspace_id: str
    conversation: Mapping[str, Any] = None  # type: ignore[assignment]
    workspace: Mapping[str, Any] = None  # type: ignore[assignment]
    core: Mapping[str, Any] = None  # type: ignore[assignment]
    runtime: Mapping[str, Any] = None  # type: ignore[assignment]
    sealed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "conversation", freeze_mapping(self.conversation))
        object.__setattr__(self, "workspace", freeze_mapping(self.workspace))
        object.__setattr__(self, "core", freeze_mapping(self.core))
        object.__setattr__(self, "runtime", freeze_mapping(self.runtime))

    def to_canonical_dict(self) -> dict[str, Any]:
        return envelope(
            kind=KIND_CONTEXT,
            payload={
                "request_id": self.request_id,
                "session_id": self.session_id,
                "workspace_id": self.workspace_id,
                "conversation": dict(self.conversation),
                "workspace": dict(self.workspace),
                "core": dict(self.core),
                "runtime": dict(self.runtime),
                "sealed": self.sealed,
            },
        )
