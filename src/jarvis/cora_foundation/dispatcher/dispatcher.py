"""Dispatcher — ToolPlan → DispatchRequest / DispatchResult (never execute adapters).

Law:
  No Adapter without Dispatcher.
  No Dispatcher without ToolPlan.
  No ToolPlan without PlannerDecision.

Does not decide tools · does not mutate ToolPlan · no Electron/UI/Persona · no live APIs.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..tool_routing.plan import ToolPlan
from .contracts import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchOutcome,
    DispatchRequest,
    DispatchResult,
)

# Known tools only — unknown → UNSUPPORTED_TOOL (no adapter invent)
_TOOL_TO_CAPABILITY: dict[str, str] = {
    "GitHub.create_pr": "github.write",
    "GitHub.create_issue": "github.write",
    "GitHub.comment_pr": "github.write",
    "GitHub.comment_issue": "github.write",
    "GitHub.read_repo": "github.read",
    "GitHub.read_pr": "github.read",
    "GitHub.list_branches": "github.read",
    "Discord.send": "discord.send",
    "Framework.run": "framework.execute",
    "Railway.deploy": "railway.deploy",
    "n8n.execute_workflow": "n8n.execute",
    "Filesystem.edit": "filesystem.write",
    "Filesystem.read": "filesystem.read",
    "ComputerOperator.act": "computer_operator.control",
}


class Dispatcher:
    """Transform an approved ToolPlan into standardized DispatchRequests."""

    def dispatch(
        self,
        plan: ToolPlan,
        *,
        approval_granted: bool = False,
        payload: Mapping[str, Any] | None = None,
    ) -> DispatchResult:
        if plan.empty:
            return DispatchResult(
                result_id=DispatchResult.new_id(),
                plan_id=plan.plan_id,
                outcome=DispatchOutcome.EMPTY,
                requests=(),
                errors=(),
                metadata={"reason": "empty_tool_plan", "adapter_invoked": False},
            )

        if plan.approval_required and not approval_granted:
            return DispatchResult(
                result_id=DispatchResult.new_id(),
                plan_id=plan.plan_id,
                outcome=DispatchOutcome.DENY,
                requests=(),
                errors=(
                    {
                        "code": "DENY",
                        "tool": "*",
                        "message": "approval_required but approval not granted",
                    },
                ),
                metadata={
                    "reason": "approval_missing",
                    "approval_required": True,
                    "adapter_invoked": False,
                },
            )

        approval_state = (
            ApprovalState.GRANTED
            if plan.approval_required
            else ApprovalState.NOT_REQUIRED
        )
        base_payload = dict(payload or {})
        requests: list[DispatchRequest] = []
        errors: list[dict[str, Any]] = []

        for index, tool in enumerate(plan.required_tools):
            capability = _TOOL_TO_CAPABILITY.get(tool)
            if capability is None:
                errors.append(
                    {
                        "code": "UNSUPPORTED_TOOL",
                        "tool": tool,
                        "message": f"no adapter mapping for tool: {tool}",
                    }
                )
                continue

            # Prefer aligned capability from plan when present
            if index < len(plan.required_capabilities):
                planned_cap = plan.required_capabilities[index]
                if planned_cap:
                    capability = planned_cap

            requests.append(
                DispatchRequest(
                    dispatch_id=DispatchRequest.new_id(),
                    plan_id=plan.plan_id,
                    tool=tool,
                    capability=capability,
                    execution_mode=DispatchExecutionMode.NONE,
                    approval_state=approval_state,
                    payload=base_payload,
                    metadata={
                        "planner_decision_id": plan.planner_decision_id,
                        "request_id": plan.request_id,
                        "tool_index": index,
                        "risk": plan.risk.value,
                        "fallback_tools": list(plan.fallback_tools),
                        "adapter_invoked": False,
                        "world_change_gate": True,
                    },
                )
            )

        if not requests and errors:
            outcome = DispatchOutcome.UNSUPPORTED_TOOL
        elif requests and errors:
            outcome = DispatchOutcome.PARTIAL
        else:
            outcome = DispatchOutcome.READY

        return DispatchResult(
            result_id=DispatchResult.new_id(),
            plan_id=plan.plan_id,
            outcome=outcome,
            requests=tuple(requests),
            errors=tuple(errors),
            metadata={
                "adapter_invoked": False,
                "request_count": len(requests),
                "error_count": len(errors),
            },
        )
