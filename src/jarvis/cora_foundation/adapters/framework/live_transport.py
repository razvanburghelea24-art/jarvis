"""Live Framework transport — game API; phase-gated; injectable HTTP."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .flags import ops_for_phase
from .transport import FrameworkTransportResult

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]

_READ_OPS = frozenset(
    {
        "server_status",
        "players",
        "world_time",
        "weather",
        "server_info",
        "health",
        "metrics",
    }
)


class LiveFrameworkTransport:
    live = True

    def __init__(
        self,
        *,
        token: str,
        phase: int = 1,
        api_base: str = "http://127.0.0.1:8787/v1",
        http: HttpFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("Framework LIVE requires a token")
        self._token = token
        self._phase = phase
        self._api_base = api_base.rstrip("/")
        self._http = http or self._default_http
        self._allowed = ops_for_phase(phase)

    def _gate(self, op: str) -> FrameworkTransportResult | None:
        if op not in self._allowed:
            return FrameworkTransportResult(
                ok=False,
                error="PHASE_LOCKED",
                data={"phase": self._phase, "operation": op},
            )
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "Cora-Framework-LIVE/1",
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
                raw = resp.read().decode("utf-8") or "{}"
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
        except urllib.error.URLError as exc:
            return 503, {"message": f"unreachable:{exc.reason}"}

    def _exec(
        self, op: str, *, server: str, payload: Mapping[str, Any]
    ) -> FrameworkTransportResult:
        locked = self._gate(op)
        if locked:
            return locked
        method = "GET" if op in _READ_OPS else "POST"
        path = f"/servers/{server}/{op}"
        url = f"{self._api_base}{path}"
        body = None if method == "GET" else json.dumps(dict(payload)).encode("utf-8")
        status, data = self._http(method, url, self._headers(), body)
        if status >= 400:
            msg = "http_error"
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or f"http_{status}")
            return FrameworkTransportResult(
                ok=False,
                error=msg,
                data=data if isinstance(data, dict) else {"raw": data},
            )
        out = data if isinstance(data, dict) else {"raw": data}
        return FrameworkTransportResult(
            ok=True,
            external_id=str(out.get("id") or server),
            data={**out, "live": True, "operation": op},
        )

    def server_status(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("server_status", server=server, payload=payload)

    def players(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("players", server=server, payload=payload)

    def world_time(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("world_time", server=server, payload=payload)

    def weather(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("weather", server=server, payload=payload)

    def server_info(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("server_info", server=server, payload=payload)

    def health(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("health", server=server, payload=payload)

    def metrics(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("metrics", server=server, payload=payload)

    def broadcast(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("broadcast", server=server, payload=payload)

    def heal(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("heal", server=server, payload=payload)

    def grow(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("grow", server=server, payload=payload)

    def teleport(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("teleport", server=server, payload=payload)

    def kick(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("kick", server=server, payload=payload)

    def ban(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("ban", server=server, payload=payload)

    def time_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("time_set", server=server, payload=payload)

    def weather_set(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("weather_set", server=server, payload=payload)

    def points(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("points", server=server, payload=payload)

    def economy(self, *, server: str, payload: Mapping[str, Any]) -> FrameworkTransportResult:
        return self._exec("economy", server=server, payload=payload)
