"""n8n Adapter — READ-ONLY surface."""

from __future__ import annotations

from ..flags import adapter_enabled
from ..types import IntegrationObject, IntegrationSource
from .base import ReadOnlyAdapter


class N8nAdapter(ReadOnlyAdapter):
    name = "n8n"
    source = IntegrationSource.N8N

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = adapter_enabled("n8n") if enabled is None else bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def health(self) -> IntegrationObject:
        return self._obj(
            kind="health",
            title="n8n adapter",
            status="ready" if self._enabled else "disabled",
            payload={"read_only": True, "live": False},
        )

    def workflows(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="workflow",
                title="(stub) no live fetch",
                status="stub",
                payload={"items": [], "live": False},
            )
        ]

    def executions(self, *, workflow_id: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="execution",
                title="(stub) no live fetch",
                status="stub",
                refs={"workflow_id": workflow_id or ""},
                payload={"items": [], "live": False},
            )
        ]

    def snapshot(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        out = [self.health()]
        out.extend(self.workflows())
        out.extend(self.executions())
        return out
