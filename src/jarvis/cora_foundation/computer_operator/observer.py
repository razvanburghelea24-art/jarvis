"""Desktop observer — READ-ONLY contract. Stub by default (no OS control libs)."""

from __future__ import annotations

from typing import Protocol

from .allowlist import AppAllowlist
from .types import (
    IndicatorState,
    MonitorInfo,
    ObservationSnapshot,
    OperatorMode,
    ProcessInfo,
    WindowInfo,
    new_snapshot_id,
)


class DesktopObserver(Protocol):
    def snapshot(
        self,
        *,
        allowlist: AppAllowlist,
        clipboard_permitted: bool,
        indicator: IndicatorState,
    ) -> ObservationSnapshot: ...


class StubDesktopObserver:
    """Contract-only observer — live=false. Safe default for Phase 6A."""

    def snapshot(
        self,
        *,
        allowlist: AppAllowlist,
        clipboard_permitted: bool,
        indicator: IndicatorState,
    ) -> ObservationSnapshot:
        windows = (
            WindowInfo(
                title="(stub) VS Code — cora_foundation",
                app_name="VS Code",
                pid=None,
                is_active=True,
                allowlisted=allowlist.is_allowed("VS Code"),
            ),
            WindowInfo(
                title="(stub) Explorer",
                app_name="Explorer",
                pid=None,
                is_active=False,
                allowlisted=allowlist.is_allowed("Explorer"),
            ),
        )
        processes = (
            ProcessInfo(name="Code", pid=1001, allowlisted=allowlist.is_allowed("Code")),
            ProcessInfo(name="explorer", pid=1002, allowlisted=allowlist.is_allowed("Explorer")),
        )
        monitors = (MonitorInfo(index=0, width=1920, height=1080, scale=1.0),)
        clip = "(stub clipboard)" if clipboard_permitted else None
        return ObservationSnapshot(
            snapshot_id=new_snapshot_id(),
            indicator=indicator,
            mode=OperatorMode.OBSERVABILITY,
            active_app="VS Code",
            windows=windows,
            mouse_position=(640, 360),
            keyboard_idle=True,
            clipboard_preview=clip,
            processes=processes,
            monitors=monitors,
            live=False,
            controls=False,
        )
