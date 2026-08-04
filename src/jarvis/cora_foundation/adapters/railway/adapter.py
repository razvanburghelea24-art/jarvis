"""Railway Adapter v1 — DispatchRequest → AdapterResult only.

Infrastructure surface — stricter than content/game adapters.
Never invents project_id/service_id. Mock transport default (live=False).
Does not know Planner / ToolRouter / Dispatcher / Electron.
100% swappable without touching Dispatcher or Core.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ...dispatcher.contracts import ApprovalState, DispatchRequest
from ..result import AdapterResult, AdapterStatus
from .transport import MockRailwayTransport, RailwayTransport

ADAPTER_ID = "railway"

_TOOL_TO_OP: dict[str, str] = {
    # harness alias — Dispatcher emits Railway.deploy
    "Railway.deploy": "deploy",
    "Railway.project_status": "project_status",
    "Railway.service_status": "service_status",
    "Railway.deployment_status": "deployment_status",
    "Railway.list_services": "list_services",
    "Railway.list_deployments": "list_deployments",
    "Railway.logs": "logs",
    "Railway.environment_info": "environment_info",
    "Railway.restart_service": "restart_service",
    "Railway.rollback": "rollback",
    "Railway.set_variable": "set_variable",
    "Railway.delete_variable": "delete_variable",
}

_READ_OPS = frozenset(
    {
        "project_status",
        "service_status",
        "deployment_status",
        "list_services",
        "list_deployments",
        "logs",
        "environment_info",
    }
)

_WRITE_OPS = frozenset(
    {
        "deploy",
        "restart_service",
        "rollback",
        "set_variable",
        "delete_variable",
    }
)

# Ops that need service_id in addition to project_id
_SERVICE_OPS = frozenset(
    {
        "service_status",
        "deployment_status",
        "list_deployments",
        "logs",
        "deploy",
        "restart_service",
        "rollback",
        "set_variable",
        "delete_variable",
    }
)


class RailwayAdapter:
    """Single entry: execute(DispatchRequest) → AdapterResult."""

    def __init__(self, transport: RailwayTransport | None = None) -> None:
        self._transport: RailwayTransport = transport or MockRailwayTransport()

    def execute(self, request: DispatchRequest | Any) -> AdapterResult:
        started = time.perf_counter()

        invalid = self._validate_request(request)
        if invalid is not None:
            return self._fail(
                request_id=getattr(request, "dispatch_id", "") or "invalid",
                operation="unknown",
                error=invalid,
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "denied": True},
            )

        assert isinstance(request, DispatchRequest)
        operation = _TOOL_TO_OP.get(request.tool)
        if operation is None:
            return self._fail(
                request_id=request.dispatch_id,
                operation=request.tool,
                error="UNSUPPORTED_OPERATION",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "tool": request.tool},
            )

        if not self._approval_ok(request, operation):
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="DENY",
                duration=time.perf_counter() - started,
                metadata={
                    "phase": "READY",
                    "approval_state": request.approval_state.value,
                    "reason": "approval_missing",
                },
            )

        project_id = str(request.payload.get("project_id") or "").strip()
        if not project_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_PROJECT",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "project_id_not_in_payload"},
            )

        service_id = str(request.payload.get("service_id") or "").strip()
        if operation in _SERVICE_OPS and not service_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_SERVICE",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "service_id_not_in_payload"},
            )

        handler = self._handlers().get(operation)
        assert handler is not None
        try:
            if operation in _SERVICE_OPS:
                tr = handler(
                    project_id=project_id,
                    service_id=service_id,
                    payload=dict(request.payload),
                )
            else:
                tr = handler(project_id=project_id, payload=dict(request.payload))
        except Exception as exc:  # noqa: BLE001 — boundary
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error=f"TRANSPORT_ERROR:{exc}",
                duration=time.perf_counter() - started,
                metadata={
                    "phase": "RUNNING",
                    "live": getattr(self._transport, "live", False),
                },
            )

        duration = time.perf_counter() - started
        if not tr.ok:
            return AdapterResult(
                status=AdapterStatus.FAILED,
                request_id=request.dispatch_id,
                adapter=ADAPTER_ID,
                operation=operation,
                external_id=tr.external_id,
                duration=duration,
                error=tr.error or "FAILED",
                metadata={
                    "phase": "RUNNING",
                    "final": "FAILED",
                    "plan_id": request.plan_id,
                    "live": getattr(self._transport, "live", False),
                    "data": dict(tr.data or {}),
                },
            )

        return AdapterResult(
            status=AdapterStatus.SUCCESS,
            request_id=request.dispatch_id,
            adapter=ADAPTER_ID,
            operation=operation,
            external_id=tr.external_id,
            duration=duration,
            error=None,
            metadata={
                "phase": "RUNNING",
                "final": "SUCCESS",
                "plan_id": request.plan_id,
                "project_id": project_id,
                "service_id": service_id or None,
                "live": getattr(self._transport, "live", False),
                "data": dict(tr.data or {}),
            },
        )

    def _handlers(self) -> dict[str, Callable[..., Any]]:
        t = self._transport
        return {
            "project_status": t.project_status,
            "service_status": t.service_status,
            "deployment_status": t.deployment_status,
            "list_services": t.list_services,
            "list_deployments": t.list_deployments,
            "logs": t.logs,
            "environment_info": t.environment_info,
            "deploy": t.deploy,
            "restart_service": t.restart_service,
            "rollback": t.rollback,
            "set_variable": t.set_variable,
            "delete_variable": t.delete_variable,
        }

    @staticmethod
    def _approval_ok(request: DispatchRequest, operation: str) -> bool:
        state = request.approval_state
        if state in {ApprovalState.DENIED, ApprovalState.PENDING}:
            return False
        if operation in _WRITE_OPS:
            return state == ApprovalState.GRANTED
        return state in {ApprovalState.GRANTED, ApprovalState.NOT_REQUIRED}

    @staticmethod
    def _validate_request(request: Any) -> str | None:
        if request is None:
            return "INVALID_DISPATCH_REQUEST"
        if not isinstance(request, DispatchRequest):
            return "INVALID_DISPATCH_REQUEST"
        if not request.dispatch_id or not request.plan_id or not request.tool:
            return "INVALID_DISPATCH_REQUEST"
        if not str(request.tool).startswith("Railway."):
            return "INVALID_DISPATCH_REQUEST"
        return None

    @staticmethod
    def _fail(
        *,
        request_id: str,
        operation: str,
        error: str,
        duration: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> AdapterResult:
        meta = {"final": "FAILED", "live": False}
        if metadata:
            meta.update(dict(metadata))
        return AdapterResult(
            status=AdapterStatus.FAILED,
            request_id=request_id,
            adapter=ADAPTER_ID,
            operation=operation,
            external_id=None,
            duration=duration,
            error=error,
            metadata=meta,
        )
