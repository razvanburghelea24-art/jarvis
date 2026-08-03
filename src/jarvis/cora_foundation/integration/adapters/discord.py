"""Discord Adapter — READ-ONLY surface."""

from __future__ import annotations

from ..flags import adapter_enabled
from ..types import IntegrationObject, IntegrationSource
from .base import ReadOnlyAdapter


class DiscordAdapter(ReadOnlyAdapter):
    name = "discord"
    source = IntegrationSource.DISCORD

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = adapter_enabled("discord") if enabled is None else bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def health(self) -> IntegrationObject:
        return self._obj(
            kind="health",
            title="Discord adapter",
            status="ready" if self._enabled else "disabled",
            payload={"read_only": True, "live": False},
        )

    def guilds(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="guild",
                title="(stub) no live fetch",
                status="stub",
                payload={"items": [], "live": False},
            )
        ]

    def channels(self, *, guild_id: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="channel",
                title="(stub) no live fetch",
                status="stub",
                refs={"guild_id": guild_id or ""},
                payload={"items": [], "live": False},
            )
        ]

    def roles(self, *, guild_id: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="role",
                title="(stub) no live fetch",
                status="stub",
                refs={"guild_id": guild_id or ""},
                payload={"items": [], "live": False},
            )
        ]

    def members(self, *, guild_id: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="member",
                title="(stub) no live fetch",
                status="stub",
                refs={"guild_id": guild_id or ""},
                payload={"items": [], "live": False},
            )
        ]

    def snapshot(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        out = [self.health()]
        out.extend(self.guilds())
        out.extend(self.channels())
        out.extend(self.roles())
        out.extend(self.members())
        return out
