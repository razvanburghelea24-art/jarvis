"""Operator indicator + observation types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class OperatorMode(str, Enum):
    OBSERVABILITY = "observability"  # Phase 6A
    ASSISTED = "assisted"  # Phase 6B — control still gated


class IndicatorState(str, Enum):
    """Mandatory visual indicator — always know operator state."""

    OBSERVE = "OBSERVE"  # 🟢
    PREVIEW = "PREVIEW"  # 🟡
    WAITING_OWNER = "WAITING_OWNER"  # 🔵
    EXECUTING = "EXECUTING"  # 🔴


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class WindowInfo:
    title: str
    app_name: str
    pid: int | None = None
    is_active: bool = False
    allowlisted: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "app_name": self.app_name,
            "pid": self.pid,
            "is_active": self.is_active,
            "allowlisted": self.allowlisted,
        }


@dataclass(frozen=True)
class ProcessInfo:
    name: str
    pid: int
    allowlisted: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {"name": self.name, "pid": self.pid, "allowlisted": self.allowlisted}


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    width: int
    height: int
    scale: float = 1.0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
        }


@dataclass(frozen=True)
class ObservationSnapshot:
    """Read-only desktop fact — no control authority."""

    snapshot_id: str
    indicator: IndicatorState
    mode: OperatorMode
    active_app: str | None
    windows: tuple[WindowInfo, ...]
    mouse_position: tuple[int, int] | None
    keyboard_idle: bool | None  # observe presence/idle — never inject keys
    clipboard_preview: str | None  # None if not permitted
    processes: tuple[ProcessInfo, ...]
    monitors: tuple[MonitorInfo, ...]
    live: bool = False
    controls: bool = False
    observed_at: str = field(default_factory=_now)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "indicator": self.indicator.value,
            "mode": self.mode.value,
            "active_app": self.active_app,
            "windows": [w.to_public_dict() for w in self.windows],
            "mouse_position": list(self.mouse_position) if self.mouse_position else None,
            "keyboard_idle": self.keyboard_idle,
            "clipboard_preview": self.clipboard_preview,
            "processes": [p.to_public_dict() for p in self.processes],
            "monitors": [m.to_public_dict() for m in self.monitors],
            "live": self.live,
            "controls": False,
            "observed_at": self.observed_at,
        }


def new_snapshot_id() -> str:
    return f"obs_{uuid.uuid4().hex[:14]}"
