"""Framework Adapter v1 — DispatchRequest → AdapterResult only.

Strictest live-integration surface: game world. Never invents server/player_id.
Default transport mock (live=False). Does not know Planner/Dispatcher/Electron.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ...dispatcher.contracts import ApprovalState, DispatchRequest
from ..result import AdapterResult, AdapterStatus
from .transport import FrameworkTransport, MockFrameworkTransport

ADAPTER_ID = "framework"

_TOOL_TO_OP: dict[str, str] = {
    # harness alias — safest read when Dispatcher emits Framework.run
    "Framework.run": "server_status",
    "Framework.server_status": "server_status",
    "Framework.players": "players",
    "Framework.world_time": "world_time",
    "Framework.weather": "weather",
    "Framework.server_info": "server_info",
    "Framework.health": "health",
    "Framework.metrics": "metrics",
    "Framework.broadcast": "broadcast",
    "Framework.heal": "heal",
    "Framework.grow": "grow",
    "Framework.teleport": "teleport",
    "Framework.kick": "kick",
    "Framework.ban": "ban",
    "Framework.time_set": "time_set",
    "Framework.weather_set": "weather_set",
    "Framework.points": "points",
    "Framework.economy": "economy",
}

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

_WRITE_OPS = frozenset(
    {
        "broadcast",
        "heal",
        "grow",
        "teleport",
        "kick",
        "ban",
        "time_set",
        "weather_set",
        "points",
        "economy",
    }
)

_PLAYER_OPS = frozenset(
    {"heal", "grow", "teleport", "kick", "ban", "points", "economy"}
)


class FrameworkAdapter:
    """Single entry: execute(DispatchRequest) → AdapterResult."""

    def __init__(self, transport: FrameworkTransport | None = None) -> None:
        self._transport: FrameworkTransport = transport or MockFrameworkTransport()

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

        server = str(request.payload.get("server") or "").strip()
        if not server:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_SERVER",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "server_not_in_payload"},
            )

        player_id = str(request.payload.get("player_id") or "").strip()
        if operation in _PLAYER_OPS and not player_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_PLAYER",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "player_id_not_in_payload"},
            )

        handler = self._handlers().get(operation)
        assert handler is not None
        try:
            tr = handler(server=server, payload=dict(request.payload))
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
                "server": server,
                "player_id": player_id or None,
                "live": getattr(self._transport, "live", False),
                "data": dict(tr.data or {}),
            },
        )

    def _handlers(self) -> dict[str, Callable[..., Any]]:
        t = self._transport
        return {
            "server_status": t.server_status,
            "players": t.players,
            "world_time": t.world_time,
            "weather": t.weather,
            "server_info": t.server_info,
            "health": t.health,
            "metrics": t.metrics,
            "broadcast": t.broadcast,
            "heal": t.heal,
            "grow": t.grow,
            "teleport": t.teleport,
            "kick": t.kick,
            "ban": t.ban,
            "time_set": t.time_set,
            "weather_set": t.weather_set,
            "points": t.points,
            "economy": t.economy,
        }

    @staticmethod
    def _approval_ok(request: DispatchRequest, operation: str) -> bool:
        state = request.approval_state
        if state in {ApprovalState.DENIED, ApprovalState.PENDING}:
            return False
        if operation in _WRITE_OPS:
            return state == ApprovalState.GRANTED
        # reads — policy may allow without approval
        return state in {ApprovalState.GRANTED, ApprovalState.NOT_REQUIRED}

    @staticmethod
    def _validate_request(request: Any) -> str | None:
        if request is None:
            return "INVALID_DISPATCH_REQUEST"
        if not isinstance(request, DispatchRequest):
            return "INVALID_DISPATCH_REQUEST"
        if not request.dispatch_id or not request.plan_id or not request.tool:
            return "INVALID_DISPATCH_REQUEST"
        if not str(request.tool).startswith("Framework."):
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
