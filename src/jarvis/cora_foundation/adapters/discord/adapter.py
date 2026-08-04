"""Discord Adapter v1 — DispatchRequest → AdapterResult only.

Law: No Adapter without Dispatcher. Never mutates ToolPlan / PlannerDecision.
Default transport is mock (live=False). Does not invent channel_id/guild_id. Does not self-approve.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ...dispatcher.contracts import ApprovalState, DispatchRequest
from ..result import AdapterResult, AdapterStatus
from .transport import DiscordTransport, MockDiscordTransport

ADAPTER_ID = "discord"

_TOOL_TO_OP: dict[str, str] = {
    "Discord.send": "send_message",
    "Discord.send_message": "send_message",
    "Discord.edit_message": "edit_message",
    "Discord.delete_message": "delete_message",
    "Discord.read_channel": "read_channel",
    "Discord.read_message": "read_message",
    "Discord.list_channels": "list_channels",
    "Discord.timeout_user": "timeout_user",
    "Discord.kick_user": "kick_user",
    "Discord.ban_user": "ban_user",
}

_WRITE_OPS = frozenset(
    {
        "send_message",
        "edit_message",
        "delete_message",
        "timeout_user",
        "kick_user",
        "ban_user",
    }
)

_CHANNEL_OPS = frozenset(
    {
        "send_message",
        "edit_message",
        "delete_message",
        "read_channel",
        "read_message",
    }
)

_GUILD_OPS = frozenset(
    {"list_channels", "timeout_user", "kick_user", "ban_user"}
)


class DiscordAdapter:
    """Single entry: execute(DispatchRequest) → AdapterResult."""

    def __init__(self, transport: DiscordTransport | None = None) -> None:
        self._transport: DiscordTransport = transport or MockDiscordTransport()

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

        channel_id = str(request.payload.get("channel_id") or "").strip()
        guild_id = str(request.payload.get("guild_id") or "").strip()

        if operation in _CHANNEL_OPS and not channel_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_CHANNEL",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "channel_id_not_in_payload"},
            )

        if operation in _GUILD_OPS and not guild_id:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_GUILD",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "guild_id_not_in_payload"},
            )

        handler = self._handlers().get(operation)
        assert handler is not None
        try:
            if operation in _CHANNEL_OPS:
                tr = handler(channel_id=channel_id, payload=dict(request.payload))
            else:
                tr = handler(guild_id=guild_id, payload=dict(request.payload))
        except Exception as exc:  # noqa: BLE001 — boundary; map to FAILED
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
                "channel_id": channel_id or None,
                "guild_id": guild_id or None,
                "live": getattr(self._transport, "live", False),
                "data": dict(tr.data or {}),
            },
        )

    def _handlers(self) -> dict[str, Callable[..., Any]]:
        t = self._transport
        return {
            "send_message": t.send_message,
            "edit_message": t.edit_message,
            "delete_message": t.delete_message,
            "read_channel": t.read_channel,
            "read_message": t.read_message,
            "list_channels": t.list_channels,
            "timeout_user": t.timeout_user,
            "kick_user": t.kick_user,
            "ban_user": t.ban_user,
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
        if not str(request.tool).startswith("Discord."):
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
