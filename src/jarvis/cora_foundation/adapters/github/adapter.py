"""GitHub Adapter v1 — DispatchRequest → AdapterResult only.

Law: No Adapter without Dispatcher. Never mutates ToolPlan / PlannerDecision.
Default transport is mock (live=False). Does not invent repo. Does not self-approve.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ...dispatcher.contracts import ApprovalState, DispatchRequest
from ..result import AdapterResult, AdapterStatus
from .transport import GitHubTransport, MockGitHubTransport

ADAPTER_ID = "github"

# Explicit operation map — nothing else
_TOOL_TO_OP: dict[str, str] = {
    "GitHub.create_pr": "create_pr",
    "GitHub.comment_pr": "comment_pr",
    "GitHub.create_issue": "create_issue",
    "GitHub.comment_issue": "comment_issue",
    "GitHub.read_repo": "read_repo",
    "GitHub.read_pr": "read_pr",
    "GitHub.list_branches": "list_branches",
}

_WRITE_OPS = frozenset(
    {"create_pr", "comment_pr", "create_issue", "comment_issue"}
)


class GitHubAdapter:
    """Single entry: execute(DispatchRequest) → AdapterResult."""

    def __init__(self, transport: GitHubTransport | None = None) -> None:
        self._transport: GitHubTransport = transport or MockGitHubTransport()

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

        # Approval gate — adapter never self-approves
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

        repo = str(request.payload.get("repo") or "").strip()
        if not repo:
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error="MISSING_REPO",
                duration=time.perf_counter() - started,
                metadata={"phase": "READY", "reason": "repo_not_in_payload"},
            )

        # READY → RUNNING
        handler = self._handlers().get(operation)
        assert handler is not None
        try:
            tr = handler(repo=repo, payload=dict(request.payload))
        except Exception as exc:  # noqa: BLE001 — boundary; map to FAILED
            return self._fail(
                request_id=request.dispatch_id,
                operation=operation,
                error=f"TRANSPORT_ERROR:{exc}",
                duration=time.perf_counter() - started,
                metadata={"phase": "RUNNING", "live": getattr(self._transport, "live", False)},
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
                "repo": repo,
                "live": getattr(self._transport, "live", False),
                "data": dict(tr.data or {}),
            },
        )

    def _handlers(self) -> dict[str, Callable[..., Any]]:
        t = self._transport
        return {
            "create_pr": t.create_pr,
            "comment_pr": t.comment_pr,
            "create_issue": t.create_issue,
            "comment_issue": t.comment_issue,
            "read_repo": t.read_repo,
            "read_pr": t.read_pr,
            "list_branches": t.list_branches,
        }

    @staticmethod
    def _approval_ok(request: DispatchRequest, operation: str) -> bool:
        state = request.approval_state
        if state == ApprovalState.DENIED:
            return False
        if state == ApprovalState.PENDING:
            return False
        if operation in _WRITE_OPS:
            # writes: must be explicitly GRANTED — adapter never self-approves
            return state == ApprovalState.GRANTED
        # reads
        return state in {
            ApprovalState.GRANTED,
            ApprovalState.NOT_REQUIRED,
        }

    @staticmethod
    def _validate_request(request: Any) -> str | None:
        if request is None:
            return "INVALID_DISPATCH_REQUEST"
        if not isinstance(request, DispatchRequest):
            return "INVALID_DISPATCH_REQUEST"
        if not request.dispatch_id or not request.plan_id or not request.tool:
            return "INVALID_DISPATCH_REQUEST"
        if not str(request.tool).startswith("GitHub."):
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
