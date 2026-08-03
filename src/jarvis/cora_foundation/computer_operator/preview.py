"""Action Preview — show intent before any control (6B). Usable in 6A for trust UX."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class PreviewStatus(str, Enum):
    DRAFT = "DRAFT"
    WAITING_OWNER = "WAITING_OWNER"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class PreviewStep:
    index: int
    description: str
    capability: str | None = None
    target_app: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "description": self.description,
            "capability": self.capability,
            "target_app": self.target_app,
        }


@dataclass(frozen=True)
class ActionPreview:
    """
    'Cora intends to: … Approve? YES/NO'
    Phase 6A can build previews; Phase 6B alone may execute after approval chain.
    """

    preview_id: str
    title: str
    steps: tuple[PreviewStep, ...]
    status: PreviewStatus = PreviewStatus.DRAFT
    requires_owner_approval: bool = True
    executable: bool = False  # always False in 6A
    created_at: str = field(default_factory=_now)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "title": self.title,
            "steps": [s.to_public_dict() for s in self.steps],
            "status": self.status.value,
            "requires_owner_approval": self.requires_owner_approval,
            "executable": False,
            "prompt": self.render_prompt(),
            "created_at": self.created_at,
        }

    def render_prompt(self) -> str:
        lines = ["Cora intends to:"]
        for step in self.steps:
            lines.append(f"{step.index}.")
            lines.append(step.description)
        lines.append("Approve?")
        lines.append("YES / NO")
        return "\n".join(lines)


def new_preview_id() -> str:
    return f"prev_{uuid.uuid4().hex[:12]}"
