"""Live n8n transport — phase-gated; injectable HTTP; Public API shape."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .flags import ops_for_phase
from .transport import N8NTransportResult

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]


class LiveN8NTransport:
    live = True

    def __init__(
        self,
        *,
        token: str,
        phase: int = 1,
        api_base: str = "http://127.0.0.1:5678/api/v1",
        http: HttpFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("n8n LIVE requires an API key")
        self._token = token
        self._phase = phase
        self._api_base = api_base.rstrip("/")
        self._http = http or self._default_http
        self._allowed = ops_for_phase(phase)

    def _gate(self, op: str) -> N8NTransportResult | None:
        if op not in self._allowed:
            return N8NTransportResult(
                ok=False,
                error="PHASE_LOCKED",
                data={"phase": self._phase, "operation": op},
            )
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._token,
            "Content-Type": "application/json",
            "User-Agent": "Cora-n8n-LIVE/1",
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
    ) -> N8NTransportResult:
        url = f"{self._api_base}{path}"
        body = None
        if method not in {"GET", "DELETE"} and payload is not None:
            body = json.dumps(dict(payload)).encode("utf-8")
        status, data = self._http(method, url, self._headers(), body)
        if status == 204:
            return N8NTransportResult(ok=True, data={"status": 204, "live": True})
        if status >= 400:
            msg = "http_error"
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or f"http_{status}")
            return N8NTransportResult(
                ok=False,
                error=msg,
                data=data if isinstance(data, dict) else {"raw": data},
            )
        if isinstance(data, list):
            return N8NTransportResult(ok=True, data={"items": data, "live": True})
        out = data if isinstance(data, dict) else {"raw": data}
        return N8NTransportResult(ok=True, data={**out, "live": True})

    def _ok(
        self, op: str, *, external_id: str, tr: N8NTransportResult
    ) -> N8NTransportResult:
        if not tr.ok:
            return tr
        data = tr.data or {}
        return N8NTransportResult(
            ok=True,
            external_id=str(
                data.get("id") or data.get("execution_id") or external_id
            ),
            data={**data, "operation": op},
        )

    def workflow_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("workflow_status")
        if locked:
            return locked
        return self._ok(
            "workflow_status",
            external_id=workflow_id,
            tr=self._request("GET", f"/workflows/{quote(workflow_id)}"),
        )

    def list_workflows(self, *, payload: Mapping[str, Any]) -> N8NTransportResult:
        locked = self._gate("list_workflows")
        if locked:
            return locked
        return self._ok(
            "list_workflows",
            external_id="n8n",
            tr=self._request("GET", "/workflows"),
        )

    def execution_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("execution_status")
        if locked:
            return locked
        eid = str(payload.get("execution_id") or "").strip()
        path = (
            f"/executions/{quote(eid)}"
            if eid
            else f"/executions?workflowId={quote(workflow_id)}&limit=1"
        )
        return self._ok(
            "execution_status",
            external_id=eid or workflow_id,
            tr=self._request("GET", path),
        )

    def execution_logs(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("execution_logs")
        if locked:
            return locked
        eid = str(payload.get("execution_id") or "").strip() or "latest"
        return self._ok(
            "execution_logs",
            external_id=eid,
            tr=self._request("GET", f"/executions/{quote(eid)}"),
        )

    def workflow_info(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("workflow_info")
        if locked:
            return locked
        return self._ok(
            "workflow_info",
            external_id=workflow_id,
            tr=self._request("GET", f"/workflows/{quote(workflow_id)}"),
        )

    def execute_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("execute_workflow")
        if locked:
            return locked
        body = {k: v for k, v in dict(payload).items() if k != "workflow_id"}
        return self._ok(
            "execute_workflow",
            external_id=workflow_id,
            tr=self._request(
                "POST", f"/workflows/{quote(workflow_id)}/run", body or {}
            ),
        )

    def activate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("activate_workflow")
        if locked:
            return locked
        return self._ok(
            "activate_workflow",
            external_id=workflow_id,
            tr=self._request(
                "POST", f"/workflows/{quote(workflow_id)}/activate", {}
            ),
        )

    def deactivate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("deactivate_workflow")
        if locked:
            return locked
        return self._ok(
            "deactivate_workflow",
            external_id=workflow_id,
            tr=self._request(
                "POST", f"/workflows/{quote(workflow_id)}/deactivate", {}
            ),
        )

    def cancel_execution(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        locked = self._gate("cancel_execution")
        if locked:
            return locked
        eid = str(payload.get("execution_id") or "").strip()
        if not eid:
            return N8NTransportResult(ok=False, error="missing_execution_id")
        return self._ok(
            "cancel_execution",
            external_id=eid,
            tr=self._request("POST", f"/executions/{quote(eid)}/stop", {}),
        )
