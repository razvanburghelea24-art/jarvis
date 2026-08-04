"""ToolRouter — PlannerDecision → ToolPlan (never execute).

Law: No tool execution without ToolPlan.
Does not call GitHub/Discord/Railway/Electron · no credentials · no Memory writes.
"""

from __future__ import annotations

import re
from typing import Any

from ..conversation.contracts import ConversationRequest
from ..planner.routing_decision import PlannerDecision, PlannerRisk, PlannerRoute
from .plan import ExecutionMode, ToolPlan, ToolRisk

# capability / keyword → (tool_id, capability_id, risk, fallback)
_CAP_TO_TOOL: dict[str, tuple[str, str, ToolRisk, tuple[str, ...]]] = {
    "github": ("GitHub.create_pr", "github.write", ToolRisk.CRITICAL, ("GitHub.create_issue",)),
    "discord": ("Discord.send", "discord.send", ToolRisk.HIGH, ()),
    "deploy": ("Railway.deploy", "railway.deploy", ToolRisk.CRITICAL, ()),
    "railway": ("Railway.deploy", "railway.deploy", ToolRisk.CRITICAL, ()),
    "framework": ("Framework.run", "framework.execute", ToolRisk.HIGH, ()),
    "filesystem": ("Filesystem.edit", "filesystem.write", ToolRisk.MEDIUM, ("Filesystem.read",)),
    "computer_operator": ("ComputerOperator.act", "computer_operator.control", ToolRisk.CRITICAL, ()),
}

_TEXT_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(github|pull\s*request|\bpr\b)", re.I), "github"),
    (re.compile(r"discord", re.I), "discord"),
    (re.compile(r"(railway|deploy)", re.I), "deploy"),
    (re.compile(r"framework", re.I), "framework"),
    (re.compile(r"(fi[sș]ier|filesystem|edit\s+file|modific[ăa]\s+fi)", re.I), "filesystem"),
)


class ToolRouter:
    """Map planner intent → ToolPlan only."""

    def route(
        self,
        planner: PlannerDecision,
        request: ConversationRequest | None = None,
    ) -> ToolPlan:
        # Direct / no plan → empty ToolPlan (LLM-only path)
        if not planner.required or planner.route == PlannerRoute.DIRECT_RESPONSE:
            return self._empty(planner, reason="direct_response_no_tools")

        caps = list(planner.required_capabilities)
        text = (request.input if request else "") or ""
        for pat, key in _TEXT_HINTS:
            if pat.search(text) and key not in caps:
                caps.append(key)

        tools: list[str] = []
        out_caps: list[str] = []
        fallbacks: list[str] = []
        max_risk = ToolRisk.NONE
        approval = bool(planner.approval_required)

        for key in caps:
            mapped = _CAP_TO_TOOL.get(key.lower())
            if mapped is None:
                continue
            tool, cap, risk, fb = mapped
            if tool not in tools:
                tools.append(tool)
            if cap not in out_caps:
                out_caps.append(cap)
            for f in fb:
                if f not in fallbacks:
                    fallbacks.append(f)
            max_risk = _max_risk(max_risk, risk)
            if risk in {ToolRisk.HIGH, ToolRisk.CRITICAL}:
                approval = True

        # analysis / implementation / planning alone → no external tools
        if not tools:
            return self._empty(
                planner,
                reason="llm_or_analysis_only",
                metadata={"planner_capabilities": list(planner.required_capabilities)},
            )

        steps = max(1, planner.estimated_steps or len(tools))
        return ToolPlan(
            plan_id=ToolPlan.new_id(),
            request_id=planner.request_id,
            planner_decision_id=planner.decision_id,
            required_tools=tuple(tools),
            required_capabilities=tuple(out_caps),
            approval_required=approval,
            execution_mode=ExecutionMode.NONE,
            estimated_cost=round(max(planner.estimated_cost, 0.1 * len(tools)), 3),
            estimated_duration_sec=float(
                max(planner.estimated_duration_sec, 15.0 * len(tools))
            ),
            risk=max_risk if max_risk != ToolRisk.NONE else _planner_risk_to_tool(planner.risk),
            fallback_tools=tuple(fallbacks),
            metadata={
                "planner_route": planner.route.value,
                "planner_reason": planner.reason,
                "steps_hint": steps,
                "world_change_gate": True,
            },
        )

    def _empty(
        self,
        planner: PlannerDecision,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> ToolPlan:
        meta = {"reason": reason, "world_change_gate": False}
        if metadata:
            meta.update(metadata)
        return ToolPlan(
            plan_id=ToolPlan.new_id(),
            request_id=planner.request_id,
            planner_decision_id=planner.decision_id,
            required_tools=(),
            required_capabilities=(),
            approval_required=False,
            execution_mode=ExecutionMode.NONE,
            estimated_cost=0.0,
            estimated_duration_sec=0.0,
            risk=ToolRisk.NONE,
            fallback_tools=(),
            metadata=meta,
        )


def _max_risk(a: ToolRisk, b: ToolRisk) -> ToolRisk:
    order = [
        ToolRisk.NONE,
        ToolRisk.LOW,
        ToolRisk.MEDIUM,
        ToolRisk.HIGH,
        ToolRisk.CRITICAL,
    ]
    return order[max(order.index(a), order.index(b))]


def _planner_risk_to_tool(risk: PlannerRisk) -> ToolRisk:
    return {
        PlannerRisk.NONE: ToolRisk.NONE,
        PlannerRisk.LOW: ToolRisk.LOW,
        PlannerRisk.MEDIUM: ToolRisk.MEDIUM,
        PlannerRisk.HIGH: ToolRisk.HIGH,
        PlannerRisk.CRITICAL: ToolRisk.CRITICAL,
    }.get(risk, ToolRisk.LOW)
