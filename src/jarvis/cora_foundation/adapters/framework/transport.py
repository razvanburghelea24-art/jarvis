"""Framework transport — injectable; default mock never hits the game server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class FrameworkTransportResult:
    ok: bool
    external_id: str | None = None
    data: Mapping[str, Any] | None = None
    error: str | None = None


class FrameworkTransport(Protocol):
    def server_status(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def players(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def world_time(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def weather(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def server_info(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def health(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def metrics(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def broadcast(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def heal(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def grow(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def teleport(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def kick(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def ban(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def time_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def weather_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def points(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...

    def economy(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult: ...


class MockFrameworkTransport:
    """Deterministic in-memory Framework — live=False always."""

    live = False

    def server_status(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True,
            external_id=server,
            data={"server": server, "online": True, "players": 3, "live": False},
        )

    def players(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True,
            external_id=server,
            data={
                "server": server,
                "players": [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}],
                "live": False,
            },
        )

    def world_time(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True, external_id=server, data={"server": server, "time": "12:00", "live": False}
        )

    def weather(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True, external_id=server, data={"server": server, "weather": "clear", "live": False}
        )

    def server_info(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True,
            external_id=server,
            data={"server": server, "name": f"fw-{server}", "version": "1.0-mock", "live": False},
        )

    def health(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True, external_id=server, data={"server": server, "ok": True, "live": False}
        )

    def metrics(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return FrameworkTransportResult(
            ok=True,
            external_id=server,
            data={"server": server, "cpu": 0.1, "mem": 0.2, "live": False},
        )

    def broadcast(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        msg = str(payload.get("message") or payload.get("content") or "").strip()
        if not msg:
            return FrameworkTransportResult(ok=False, error="missing_message")
        eid = f"bcast_{uuid4().hex[:8]}"
        return FrameworkTransportResult(
            ok=True, external_id=eid, data={"server": server, "message": msg, "live": False}
        )

    def heal(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "heal", "live": False}
        )

    def grow(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "grow", "live": False}
        )

    def teleport(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True,
            external_id=pid,
            data={"server": server, "player_id": pid, "action": "teleport", "live": False},
        )

    def kick(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "kick", "live": False}
        )

    def ban(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "ban", "live": False}
        )

    def time_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        t = str(payload.get("time") or "").strip()
        if not t:
            return FrameworkTransportResult(ok=False, error="missing_time")
        return FrameworkTransportResult(
            ok=True, external_id=server, data={"server": server, "time": t, "live": False}
        )

    def weather_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        w = str(payload.get("weather") or "").strip()
        if not w:
            return FrameworkTransportResult(ok=False, error="missing_weather")
        return FrameworkTransportResult(
            ok=True, external_id=server, data={"server": server, "weather": w, "live": False}
        )

    def points(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "points", "live": False}
        )

    def economy(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        pid = str(payload.get("player_id") or "")
        return FrameworkTransportResult(
            ok=True, external_id=pid, data={"server": server, "player_id": pid, "action": "economy", "live": False}
        )
