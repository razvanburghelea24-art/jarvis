"""Standard Integration Object — one shape for all external reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class IntegrationSource(str, Enum):
    GITHUB = "github"
    RAILWAY = "railway"
    DISCORD = "discord"
    FRAMEWORK = "framework"
    N8N = "n8n"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class IntegrationObject:
    """Normalized external fact — no authority, no side effects."""

    object_id: str
    source: IntegrationSource
    kind: str
    title: str | None = None
    status: str | None = None
    refs: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=_now)
    read_only: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "source": self.source.value,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "refs": dict(self.refs),
            "payload": dict(self.payload),
            "fetched_at": self.fetched_at,
            "read_only": True,
        }


def new_object_id(source: IntegrationSource, kind: str) -> str:
    return f"io_{source.value}_{kind}_{uuid.uuid4().hex[:12]}"
