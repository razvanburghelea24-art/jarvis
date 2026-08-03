"""Framework Adapter — READ-ONLY surface (no restart API)."""

from __future__ import annotations

from ..flags import adapter_enabled
from ..types import IntegrationObject, IntegrationSource
from .base import ReadOnlyAdapter


class FrameworkAdapter(ReadOnlyAdapter):
    name = "framework"
    source = IntegrationSource.FRAMEWORK

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = adapter_enabled("framework") if enabled is None else bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def health(self) -> IntegrationObject:
        return self._obj(
            kind="health",
            title="Framework adapter",
            status="ready" if self._enabled else "disabled",
            payload={"read_only": True, "live": False, "restart_api": False},
        )

    def status(self) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="status",
            title="(stub) no live fetch",
            status="stub",
            payload={"live": False},
        )

    def players(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="player",
                title="(stub) no live fetch",
                status="stub",
                payload={"items": [], "live": False},
            )
        ]

    def weather(self) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="weather",
            title="(stub) no live fetch",
            status="stub",
            payload={"live": False},
        )

    def time(self) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="time",
            title="(stub) no live fetch",
            status="stub",
            payload={"live": False},
        )

    def snapshot(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        out = [self.health()]
        st = self.status()
        if st is not None:
            out.append(st)
        out.extend(self.players())
        w = self.weather()
        if w is not None:
            out.append(w)
        t = self.time()
        if t is not None:
            out.append(t)
        return out
