"""ConversationResponse — streamed / final user-facing text (v1 frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .schema import KIND_RESPONSE, envelope, freeze_mapping
from .state import LifecyclePhase


@dataclass(frozen=True)
class ConversationResponse:
    response_id: str
    request_id: str
    decision_id: str | None
    phase: LifecyclePhase
    text: str = ""
    incomplete: bool = False
    tool_summary: str | None = None
    citations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.phase, str):
            object.__setattr__(self, "phase", LifecyclePhase(self.phase))
        if isinstance(self.citations, list):
            object.__setattr__(self, "citations", tuple(self.citations))

    def to_canonical_dict(self) -> dict[str, Any]:
        return envelope(
            kind=KIND_RESPONSE,
            payload={
                "response_id": self.response_id,
                "request_id": self.request_id,
                "decision_id": self.decision_id,
                "phase": self.phase.value,
                "text": self.text,
                "incomplete": self.incomplete,
                "tool_summary": self.tool_summary,
                "citations": list(self.citations),
                "metadata": dict(self.metadata),
            },
        )
