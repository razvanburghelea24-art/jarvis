"""n8n Adapter v1 — DispatchRequest → AdapterResult only.

Last Integration Layer v1 adapter. Never invents workflow_id/execution_id.
Mock transport default (live=False). Does not know Planner/ToolRouter/Dispatcher/Electron/UI.
100% swappable without touching Dispatcher or Core.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ...dispatcher.contracts import ApprovalState, DispatchRequest
from ..result import AdapterResult, AdapterStatus
from .transport import MockN8NTransport, N8NTransport

ADAPTER_ID = "n8n"

_TOOL_TO_OP: dict[str, str] = {
    "n8n.workflow_status": "workflow_status",
    "n8n.list_workflows": "list_workflows",
    "n8n.execution_status": "execution_status",
    "n8n.execution_logs": "execution_logs",
    "n8n.workflow_info": "workflow_info",
    "n8n.execute_workflow": "execute_workflow",
    "n8n.activate_workflow": "activate_workflow",
    "n8n.deactivate_workflow": "deactivate_workflow",
    "n8n.cancel_execution": "cancel_execution",
}

_WRITE_OPS = frozenset(
    {
        "execute_workflow",
        "activate_workflow",
        "deactivate_workflow",
        "cancel_execution",
    }
)

_WORKFLOW_OPS = frozenset(
    {
        "workflow_status",
        "execution_status",
        "execution_logs",
        "workflow_info",
        "execute_workflow",
        "activate_workflow",
        "deactivate_workflow",
        "cancel_execution",
    }
)


class N8NAdapter:
    """Single entry: execute(DispatchRequest) → AdapterResult."""

    def __init__(self, transport: N8NTransport | None = None) -> None:
        self._transport: N8NTransport = transport or MockN8NTransport()

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

        workflow_id = str(request.payload.get("workflow_id") or "").strip()
        if operation in _WORKFLOW_OPS and not workflow_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_WORKFLOW",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "workflow_id_not_in_payload"},
            )

        handler = self._handlers().get(operation)
        assert handler is not None
        try:
            if operation == "list_workflows":
                tr = handler(payload=dict(request.payload))
            else:
                tr = handler(workflow_id=workflow_id, payload=dict(request.payload))
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
                "workflow_id": workflow_id or None,
                "live": getattr(self._transport, "live", False),
                "data": dict(tr.data or {}),
            },
        )

    def _handlers(self) -> dict[str, Callable[..., Any]]:
        t = self._transport
        return {
            "workflow_status": t.workflow_status,
            "list_workflows": t.list_workflows,
            "execution_status": t.execution_status,
            "execution_logs": t.execution_logs,
            "workflow_info": t.workflow_info,
            "execute_workflow": t.execute_workflow,
            "activate_workflow": t.activate_workflow,
            "deactivate_workflow": t.deactivate_workflow,
            "cancel_execution": t.cancel_execution,
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
        if not str(request.tool).startswith("n8n."):
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
