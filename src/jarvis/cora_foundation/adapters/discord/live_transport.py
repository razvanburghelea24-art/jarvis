"""Live Discord transport — Bot API; phase-gated; injectable HTTP for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .flags import ops_for_phase
from .transport import DiscordTransportResult

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]


class LiveDiscordTransport:
    live = True

    def __init__(
        self,
        *,
        token: str,
        phase: int = 1,
        api_base: str = "https://discord.com/api/v10",
        http: HttpFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("Discord LIVE requires a bot token")
        self._token = token
        self._phase = phase
        self._api_base = api_base.rstrip("/")
        self._http = http or self._default_http
        self._allowed = ops_for_phase(phase)

    def _gate(self, op: str) -> DiscordTransportResult | None:
        if op not in self._allowed:
            return DiscordTransportResult(
                ok=False,
                error="PHASE_LOCKED",
                data={"phase": self._phase, "operation": op},
            )
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "Cora-Discord-LIVE/1",
        }

    def _default_http(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: bytes | None,
    ) -> tuple[int, Any]:
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8") or "null"
                data = json.loads(raw) if raw.strip() else {}
                return int(resp.status), data
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"message": raw}
            if isinstance(data, dict):
                data = {**data, "status": exc.code}
            return int(exc.code), data

    def _call(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> DiscordTransportResult:
        url = f"{self._api_base}{path}"
        body = (
            json.dumps(dict(payload or {})).encode("utf-8") if payload is not None else None
        )
        if method in {"GET", "DELETE"}:
            body = None if method == "GET" else body
        if method == "DELETE" and payload is None:
            body = None
        status, data = self._http(method, url, self._headers(), body)
        if status == 204:
            return DiscordTransportResult(ok=True, data={"status": 204})
        if status >= 400:
            msg = "http_error"
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or f"http_{status}")
            return DiscordTransportResult(
                ok=False,
                error=msg,
                data=data if isinstance(data, dict) else {"raw": data},
            )
        if isinstance(data, list):
            return DiscordTransportResult(ok=True, data={"items": data})
        return DiscordTransportResult(
            ok=True, data=data if isinstance(data, dict) else {"raw": data}
        )

    def read_channel(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("read_channel")
        if locked:
            return locked
        tr = self._call("GET", f"/channels/{channel_id}")
        if tr.ok:
            return DiscordTransportResult(
                ok=True,
                external_id=channel_id,
                data={**(tr.data or {}), "live": True},
            )
        return tr

    def read_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("read_message")
        if locked:
            return locked
        mid = str(payload.get("message_id") or "").strip()
        if not mid:
            return DiscordTransportResult(ok=False, error="missing_message_id")
        tr = self._call("GET", f"/channels/{channel_id}/messages/{mid}")
        if tr.ok:
            return DiscordTransportResult(
                ok=True, external_id=mid, data={**(tr.data or {}), "live": True}
            )
        return tr

    def list_channels(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("list_channels")
        if locked:
            return locked
        tr = self._call("GET", f"/guilds/{guild_id}/channels")
        if tr.ok:
            items = (tr.data or {}).get("items") or []
            chans = [
                {"id": c.get("id"), "name": c.get("name")}
                for c in items
                if isinstance(c, dict)
            ]
            return DiscordTransportResult(
                ok=True,
                external_id=guild_id,
                data={"guild_id": guild_id, "channels": chans, "live": True},
            )
        return tr

    def send_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("send_message")
        if locked:
            return locked
        content = str(payload.get("content") or "").strip()
        if not content:
            return DiscordTransportResult(ok=False, error="missing_content")
        tr = self._call("POST", f"/channels/{channel_id}/messages", {"content": content})
        if tr.ok:
            mid = str((tr.data or {}).get("id") or "")
            return DiscordTransportResult(
                ok=True, external_id=mid, data={**(tr.data or {}), "live": True}
            )
        return tr

    def edit_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("edit_message")
        if locked:
            return locked
        mid = str(payload.get("message_id") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not mid or not content:
            return DiscordTransportResult(ok=False, error="missing_message_id_or_content")
        tr = self._call(
            "PATCH",
            f"/channels/{channel_id}/messages/{mid}",
            {"content": content},
        )
        if tr.ok:
            return DiscordTransportResult(
                ok=True, external_id=mid, data={**(tr.data or {}), "live": True}
            )
        return tr

    def delete_message(
        self, *, channel_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("delete_message")
        if locked:
            return locked
        mid = str(payload.get("message_id") or "").strip()
        if not mid:
            return DiscordTransportResult(ok=False, error="missing_message_id")
        tr = self._call("DELETE", f"/channels/{channel_id}/messages/{mid}")
        if tr.ok:
            return DiscordTransportResult(
                ok=True,
                external_id=mid,
                data={
                    "channel_id": channel_id,
                    "message_id": mid,
                    "deleted": True,
                    "live": True,
                },
            )
        return tr

    def timeout_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("timeout_user")
        if locked:
            return locked
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        until = str(payload.get("until") or "2026-01-01T00:00:00.000Z")
        tr = self._call(
            "PATCH",
            f"/guilds/{guild_id}/members/{uid}",
            {"communication_disabled_until": until},
        )
        if tr.ok:
            return DiscordTransportResult(
                ok=True,
                external_id=uid,
                data={**(tr.data or {}), "live": True, "action": "timeout"},
            )
        return tr

    def kick_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("kick_user")
        if locked:
            return locked
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        tr = self._call("DELETE", f"/guilds/{guild_id}/members/{uid}")
        if tr.ok:
            return DiscordTransportResult(
                ok=True,
                external_id=uid,
                data={"guild_id": guild_id, "user_id": uid, "action": "kick", "live": True},
            )
        return tr

    def ban_user(
        self, *, guild_id: str, payload: Mapping[str, Any]
    ) -> DiscordTransportResult:
        locked = self._gate("ban_user")
        if locked:
            return locked
        uid = str(payload.get("user_id") or "").strip()
        if not uid:
            return DiscordTransportResult(ok=False, error="missing_user_id")
        tr = self._call("PUT", f"/guilds/{guild_id}/bans/{uid}", {})
        if tr.ok:
            return DiscordTransportResult(
                ok=True,
                external_id=uid,
                data={"guild_id": guild_id, "user_id": uid, "action": "ban", "live": True},
            )
        return tr
