"""Railway Adapter — READ-ONLY surface."""

from __future__ import annotations

from ..flags import adapter_enabled
from ..types import IntegrationObject, IntegrationSource
from .base import ReadOnlyAdapter


class RailwayAdapter(ReadOnlyAdapter):
    name = "railway"
    source = IntegrationSource.RAILWAY

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = adapter_enabled("railway") if enabled is None else bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def health(self) -> IntegrationObject:
        return self._obj(
            kind="health",
            title="Railway adapter",
            status="ready" if self._enabled else "disabled",
            payload={"read_only": True, "live": False},
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

    def deployments(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="deployment",
                title="(stub) no live fetch",
                status="stub",
                payload={"items": [], "live": False},
            )
        ]

    def logs(self, *, deployment_id: str | None = None) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="logs",
            title="(stub) no live fetch",
            status="stub",
            refs={"deployment_id": deployment_id or ""},
            payload={"lines": [], "live": False},
        )

    def snapshot(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        out = [self.health()]
        st = self.status()
        if st is not None:
            out.append(st)
        out.extend(self.deployments())
        return out
