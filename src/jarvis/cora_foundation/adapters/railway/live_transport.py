"""Live Railway transport — phase-gated; injectable HTTP; Cora REST shape."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .flags import ops_for_phase
from .transport import RailwayTransportResult

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]


class LiveRailwayTransport:
    live = True

    def __init__(
        self,
        *,
        token: str,
        phase: int = 1,
        api_base: str = "https://backboard.railway.app/v1",
        http: HttpFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("Railway LIVE requires a token")
        self._token = token
        self._phase = phase
        self._api_base = api_base.rstrip("/")
        self._http = http or self._default_http
        self._allowed = ops_for_phase(phase)

    def _gate(self, op: str) -> RailwayTransportResult | None:
        if op not in self._allowed:
            return RailwayTransportResult(
                ok=False,
                error="PHASE_LOCKED",
                data={"phase": self._phase, "operation": op},
            )
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "Cora-Railway-LIVE/1",
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

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> RailwayTransportResult:
        url = f"{self._api_base}{path}"
        body = None
        if method not in {"GET", "DELETE"} and payload is not None:
            body = json.dumps(dict(payload)).encode("utf-8")
        status, data = self._http(method, url, self._headers(), body)
        if status == 204:
            return RailwayTransportResult(ok=True, data={"status": 204, "live": True})
        if status >= 400:
            msg = "http_error"
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or f"http_{status}")
            return RailwayTransportResult(
                ok=False,
                error=msg,
                data=data if isinstance(data, dict) else {"raw": data},
            )
        out = data if isinstance(data, dict) else {"raw": data}
        return RailwayTransportResult(ok=True, data={**out, "live": True})

    def _ok(
        self,
        op: str,
        *,
        external_id: str,
        tr: RailwayTransportResult,
    ) -> RailwayTransportResult:
        if not tr.ok:
            return tr
        return RailwayTransportResult(
            ok=True,
            external_id=str(
                (tr.data or {}).get("id")
                or (tr.data or {}).get("deployment_id")
                or external_id
            ),
            data={**(tr.data or {}), "operation": op},
        )

    def project_status(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("project_status")
        if locked:
            return locked
        return self._ok(
            "project_status",
            external_id=project_id,
            tr=self._request("GET", f"/projects/{quote(project_id)}"),
        )

    def list_services(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("list_services")
        if locked:
            return locked
        return self._ok(
            "list_services",
            external_id=project_id,
            tr=self._request("GET", f"/projects/{quote(project_id)}/services"),
        )

    def environment_info(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("environment_info")
        if locked:
            return locked
        return self._ok(
            "environment_info",
            external_id=project_id,
            tr=self._request("GET", f"/projects/{quote(project_id)}/environment"),
        )

    def service_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("service_status")
        if locked:
            return locked
        return self._ok(
            "service_status",
            external_id=service_id,
            tr=self._request(
                "GET",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}",
            ),
        )

    def deployment_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("deployment_status")
        if locked:
            return locked
        dep = str(payload.get("deployment_id") or "").strip()
        path = (
            f"/projects/{quote(project_id)}/services/{quote(service_id)}/deployments/{quote(dep)}"
            if dep
            else f"/projects/{quote(project_id)}/services/{quote(service_id)}/deployments/latest"
        )
        return self._ok(
            "deployment_status",
            external_id=dep or service_id,
            tr=self._request("GET", path),
        )

    def list_deployments(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("list_deployments")
        if locked:
            return locked
        return self._ok(
            "list_deployments",
            external_id=service_id,
            tr=self._request(
                "GET",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/deployments",
            ),
        )

    def logs(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("logs")
        if locked:
            return locked
        return self._ok(
            "logs",
            external_id=service_id,
            tr=self._request(
                "GET",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/logs",
            ),
        )

    def deploy(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("deploy")
        if locked:
            return locked
        return self._ok(
            "deploy",
            external_id=service_id,
            tr=self._request(
                "POST",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/deploy",
                payload,
            ),
        )

    def restart_service(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("restart_service")
        if locked:
            return locked
        return self._ok(
            "restart_service",
            external_id=service_id,
            tr=self._request(
                "POST",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/restart",
                payload,
            ),
        )

    def rollback(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("rollback")
        if locked:
            return locked
        return self._ok(
            "rollback",
            external_id=str(payload.get("deployment_id") or service_id),
            tr=self._request(
                "POST",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/rollback",
                payload,
            ),
        )

    def set_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("set_variable")
        if locked:
            return locked
        key = str(payload.get("key") or "").strip()
        if not key:
            return RailwayTransportResult(ok=False, error="missing_key")
        return self._ok(
            "set_variable",
            external_id=key,
            tr=self._request(
                "PUT",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}/variables",
                payload,
            ),
        )

    def delete_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        locked = self._gate("delete_variable")
        if locked:
            return locked
        key = str(payload.get("key") or "").strip()
        if not key:
            return RailwayTransportResult(ok=False, error="missing_key")
        return self._ok(
            "delete_variable",
            external_id=key,
            tr=self._request(
                "DELETE",
                f"/projects/{quote(project_id)}/services/{quote(service_id)}"
                f"/variables/{quote(key)}",
            ),
        )
