"""Integration Hub — normalize only. No decide / write / AI."""

from __future__ import annotations

from typing import Any

from .adapters import (
    DiscordAdapter,
    FrameworkAdapter,
    GitHubAdapter,
    N8nAdapter,
    RailwayAdapter,
    ReadOnlyAdapter,
)
from .flags import hub_enabled_from_env
from .types import IntegrationObject, IntegrationSource, new_object_id

_FORBIDDEN_WRITE_METHODS = (
    "write",
    "create",
    "update",
    "delete",
    "patch",
    "post",
    "send",
    "deploy",
    "restart",
    "merge",
    "push",
    "execute",
    "trigger",
)


class IntegrationHub:
    """
    Single normalization surface for all external integrations.

    Identity is NOT resolved here — Gateway injects identity upstream.
    Memory is NOT written here — callers may snapshot → Memory later.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        adapters: dict[str, ReadOnlyAdapter] | None = None,
    ) -> None:
        self._enabled = hub_enabled_from_env() if enabled is None else bool(enabled)
        if adapters is not None:
            self._adapters = dict(adapters)
        else:
            # Construct with enabled=False so env alone doesn't leak; hub gates usage.
            self._adapters = {
                "github": GitHubAdapter(enabled=False),
                "railway": RailwayAdapter(enabled=False),
                "discord": DiscordAdapter(enabled=False),
                "framework": FrameworkAdapter(enabled=False),
                "n8n": N8nAdapter(enabled=False),
            }

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def enable_adapter(self, name: str, enabled: bool = True) -> None:
        adapter = self._adapters.get(str(name).lower())
        if adapter is None:
            raise KeyError(f"unknown adapter: {name}")
        adapter.set_enabled(enabled)

    def get_adapter(self, name: str) -> ReadOnlyAdapter | None:
        return self._adapters.get(str(name).lower())

    def list_adapters(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "source": adapter.source.value,
                "enabled": adapter.is_enabled(),
                "hub_enabled": self._enabled,
            }
            for name, adapter in sorted(self._adapters.items())
        ]

    def normalize(
        self,
        *,
        source: IntegrationSource | str,
        kind: str,
        title: str | None = None,
        status: str | None = None,
        refs: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> IntegrationObject:
        """Hub-only job: raw external fact → Integration Object."""
        src = source if isinstance(source, IntegrationSource) else IntegrationSource(str(source))
        return IntegrationObject(
            object_id=new_object_id(src, kind),
            source=src,
            kind=kind,
            title=title,
            status=status,
            refs=dict(refs or {}),
            payload=dict(payload or {}),
            read_only=True,
        )

    def snapshot(self, *, adapter: str | None = None) -> list[IntegrationObject]:
        """Read-only snapshot. Empty when hub OFF."""
        if not self._enabled:
            return []
        if adapter is not None:
            a = self.get_adapter(adapter)
            if a is None or not a.is_enabled():
                return []
            return list(a.snapshot())
        out: list[IntegrationObject] = []
        for a in self._adapters.values():
            if a.is_enabled():
                out.extend(a.snapshot())
        return out

    def status(self) -> dict[str, Any]:
        return {
            "hub_enabled": self._enabled,
            "read_only": True,
            "writes_allowed": False,
            "adapters": self.list_adapters(),
            "forbidden_write_methods": list(_FORBIDDEN_WRITE_METHODS),
        }


_HUB: IntegrationHub | None = None


def get_integration_hub() -> IntegrationHub:
    global _HUB
    if _HUB is None:
        _HUB = IntegrationHub()
    return _HUB


def reset_integration_hub_for_tests() -> None:
    global _HUB
    _HUB = None
