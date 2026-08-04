"""Discord transport — injectable; default mock never hits the network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class DiscordTransportResult:
    ok: bool
    external_id: str | None = None
    data: Mapping[str, Any] | None = None
    error: str | None = None


class DiscordTransport(Protocol):
    def send_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def edit_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def delete_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def read_channel(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def read_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def list_channels(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def timeout_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def kick_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...

    def ban_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult: ...


class MockDiscordTransport:
    """Deterministic in-memory Discord — live=False always."""

    live = False

    def send_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        content = str(payload.get("content") or "").strip()
        if not content:
            return DiscordTransportResult(ok=False, error="missing_content")
        mid = f"msg_{uuid4().hex[:10]}"
        return DiscordTransportResult(
            ok=True,
            external_id=mid,
            data={"channel_id": channel_id, "content": content, "live": False},
        )

    def edit_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        mid = str(payload.get("message_id") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not mid or not content:
            return DiscordTransportResult(ok=False, error="missing_message_id_or_content")
        return DiscordTransportResult(
            ok=True,
            external_id=mid,
            data={"channel_id": channel_id, "message_id": mid, "content": content, "live": False},
        )

    def delete_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        mid = str(payload.get("message_id") or "").strip()
        if not mid:
            return DiscordTransportResult(ok=False, error="missing_message_id")
        return DiscordTransportResult(
            ok=True,
            external_id=mid,
            data={"channel_id": channel_id, "message_id": mid, "deleted": True, "live": False},
        )

    def read_channel(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        return DiscordTransportResult(
            ok=True,
            external_id=channel_id,
            data={"channel_id": channel_id, "name": f"channel-{channel_id[-4:]}", "live": False},
        )

    def read_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        mid = str(payload.get("message_id") or "").strip()
        if not mid:
            return DiscordTransportResult(ok=False, error="missing_message_id")
        return DiscordTransportResult(
            ok=True,
            external_id=mid,
            data={
                "channel_id": channel_id,
                "message_id": mid,
                "content": "(stub)",
                "live": False,
            },
        )

    def list_channels(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        return DiscordTransportResult(
            ok=True,
            external_id=guild_id,
            data={
                "guild_id": guild_id,
                "channels": [{"id": "c1", "name": "general"}, {"id": "c2", "name": "ops"}],
                "live": False,
            },
        )

    def timeout_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        return DiscordTransportResult(
            ok=True,
            external_id=uid,
            data={"guild_id": guild_id, "user_id": uid, "action": "timeout", "live": False},
        )

    def kick_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        return DiscordTransportResult(
            ok=True,
            external_id=uid,
            data={"guild_id": guild_id, "user_id": uid, "action": "kick", "live": False},
        )

    def ban_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        return DiscordTransportResult(
            ok=True,
            external_id=uid,
            data={"guild_id": guild_id, "user_id": uid, "action": "ban", "live": False},
        )
