"""Deterministic plan synthesis — no LLM, no APIs, no execution."""

from __future__ import annotations

import re
import uuid
from typing import Any

from ..gateway.capabilities import CapabilityRegistry, default_capability_registry
from ..gateway.types import RiskLevel as CapRisk
from .context import PlannerContext
from .types import Plan, PlanKind, PlanRiskLevel, PlanStatus, PlanStep, new_plan_id


# keyword → (PlanKind, capabilities)
_KIND_HINTS: tuple[tuple[re.Pattern[str], PlanKind], ...] = (
    (re.compile(r"\brollback\b", re.I), PlanKind.ROLLBACK),
    (re.compile(r"\brelease\b|\bship\b|\bdeploy\b", re.I), PlanKind.RELEASE),
    (re.compile(r"\bmigrat", re.I), PlanKind.MIGRATION),
    (re.compile(r"\bclean\s*up\b|\bcleanup\b|\bprune\b", re.I), PlanKind.CLEANUP),
    (re.compile(r"\breview\b|\baudit\b", re.I), PlanKind.REVIEW),
    (re.compile(r"\bresearch\b|\binvestigat|\blook\s*up\b", re.I), PlanKind.RESEARCH),
    (re.compile(r"\bdiagnos|\bdebug|\bfail|\berror|\boutage\b", re.I), PlanKind.DIAGNOSIS),
    (re.compile(r"\bimplement|\bfix\b|\badd\b|\bbuild\b|\brefactor\b", re.I), PlanKind.IMPLEMENTATION),
    (re.compile(r"\banalys|\bstatus\b|\bhealth\b|\bsummary\b", re.I), PlanKind.ANALYSIS),
)

_CAP_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(pr|pull\s*request)\b", re.I), "GitHub.create_pr"),
    (re.compile(r"\bdeploy\b|\brailway\b", re.I), "Railway.deploy"),
    (re.compile(r"\bdiscord\b.*\bsend\b|\bsend\b.*\bdiscord\b|\bannounce\b", re.I), "Discord.send"),
    (re.compile(r"\brestart\b.*\bserver\b|\bserver\b.*\brestart\b", re.I), "Server.restart"),
    (re.compile(r"\boverlay\b", re.I), "Overlay.refresh"),
    (re.compile(r"\bwhoami\b|\bidentity\b", re.I), "Identity.whoami"),
    (re.compile(r"\bmemory\b", re.I), "Memory.read"),
    (re.compile(r"\bworkspace\b|\bscan\b", re.I), "Workspace.scan"),
)

_CAP_TO_PLAN_RISK = {
    CapRisk.READ: PlanRiskLevel.LOW,
    CapRisk.SAFE_LOCAL: PlanRiskLevel.LOW,
    CapRisk.OWNER_CONFIRM: PlanRiskLevel.HIGH,
    CapRisk.CRITICAL: PlanRiskLevel.CRITICAL,
    CapRisk.FORBIDDEN: PlanRiskLevel.CRITICAL,
}

_KIND_BASE_COST = {
    PlanKind.ANALYSIS: 0.1,
    PlanKind.DIAGNOSIS: 0.2,
    PlanKind.RESEARCH: 0.25,
    PlanKind.REVIEW: 0.3,
    PlanKind.CLEANUP: 0.4,
    PlanKind.IMPLEMENTATION: 0.8,
    PlanKind.MIGRATION: 1.2,
    PlanKind.RELEASE: 1.5,
    PlanKind.ROLLBACK: 1.0,
}

_KIND_BASE_DURATION = {
    PlanKind.ANALYSIS: 30.0,
    PlanKind.DIAGNOSIS: 60.0,
    PlanKind.RESEARCH: 90.0,
    PlanKind.REVIEW: 120.0,
    PlanKind.CLEANUP: 180.0,
    PlanKind.IMPLEMENTATION: 600.0,
    PlanKind.MIGRATION: 900.0,
    PlanKind.RELEASE: 450.0,
    PlanKind.ROLLBACK: 300.0,
}


def _infer_kind(text: str) -> PlanKind:
    for pattern, kind in _KIND_HINTS:
        if pattern.search(text):
            return kind
    return PlanKind.ANALYSIS


def _infer_capabilities(text: str) -> list[str]:
    found: list[str] = []
    for pattern, cap in _CAP_HINTS:
        if pattern.search(text) and cap not in found:
            found.append(cap)
    if not found:
        found.append("Memory.read")
    return found


def _risk_for(
    capabilities: list[str],
    registry: CapabilityRegistry,
) -> tuple[PlanRiskLevel, str]:
    worst = PlanRiskLevel.LOW
    reasons: list[str] = []
    order = [PlanRiskLevel.LOW, PlanRiskLevel.MEDIUM, PlanRiskLevel.HIGH, PlanRiskLevel.CRITICAL]
    for cap in capabilities:
        spec = registry.get(cap)
        if spec is None:
            level = PlanRiskLevel.MEDIUM
            reasons.append(f"{cap}: unknown capability → MEDIUM")
        else:
            level = _CAP_TO_PLAN_RISK.get(spec.risk_level, PlanRiskLevel.MEDIUM)
            reasons.append(f"{cap}: gateway={spec.risk_level.value} → {level.value}")
        if order.index(level) > order.index(worst):
            worst = level
    if not reasons:
        reasons.append("no elevated capabilities")
    return worst, "; ".join(reasons)


def synthesize_plan(
    ctx: PlannerContext,
    *,
    registry: CapabilityRegistry | None = None,
    plan_id: str | None = None,
    status: PlanStatus = PlanStatus.READY,
) -> Plan:
    """Build a Plan from context. Pure function — no I/O, no execution."""
    caps_reg = registry or default_capability_registry()
    text = (ctx.request_text or "").strip()
    kind = _infer_kind(text)
    capabilities = _infer_capabilities(text)
    risk, risk_reason = _risk_for(capabilities, caps_reg)

    # Runtime / policy may elevate approval requirement without executing.
    policy = ctx.policy_context or {}
    runtime = ctx.runtime_state or {}
    requires_approval = (
        risk in {PlanRiskLevel.HIGH, PlanRiskLevel.CRITICAL}
        or bool(policy.get("requires_owner_approval"))
        or bool(runtime.get("e_stop"))
        or bool(runtime.get("safe_mode") and risk != PlanRiskLevel.LOW)
    )

    steps: list[PlanStep] = []
    steps.append(
        PlanStep(
            step_id=f"step_{uuid.uuid4().hex[:8]}",
            title="Observe context (identity, memory, hub snapshots)",
            capability="Memory.read",
            notes="Read-only observation — no writes",
        )
    )
    prev = steps[0].step_id
    for cap in capabilities:
        if cap == "Memory.read" and len(capabilities) == 1:
            continue
        sid = f"step_{uuid.uuid4().hex[:8]}"
        steps.append(
            PlanStep(
                step_id=sid,
                title=f"Propose capability: {cap}",
                capability=cap,
                depends_on=(prev,),
                notes="Capability mapped for Dispatcher — not invoked by Planner",
            )
        )
        prev = sid
    steps.append(
        PlanStep(
            step_id=f"step_{uuid.uuid4().hex[:8]}",
            title="Await Owner/Agent execution decision",
            depends_on=(prev,),
            notes="Planner stops here — Agents execute later",
        )
    )

    hub_n = len(ctx.integration_snapshots)
    mem_n = int((ctx.memory_snapshot or {}).get("record_count") or 0)
    summary = (
        f"{kind.value} plan for request {ctx.request_id}: "
        f"{len(capabilities)} capability(ies), hub_snapshots={hub_n}, memory_records={mem_n}."
    )

    cost = _KIND_BASE_COST[kind] + 0.15 * max(0, len(capabilities) - 1)
    duration = _KIND_BASE_DURATION[kind] + 30.0 * max(0, len(capabilities) - 1)
    if risk == PlanRiskLevel.CRITICAL:
        cost *= 1.5
        duration *= 1.25

    deps: list[str] = []
    if hub_n:
        deps.append("integration_hub.snapshot")
    if mem_n:
        deps.append("memory.snapshot")
    if ctx.identity.get("who") or ctx.identity.get("owner"):
        deps.append("identity.snapshot")

    goal = text[:240] if text else f"{kind.value} of current system state"

    return Plan(
        plan_id=plan_id or new_plan_id(),
        goal=goal,
        summary=summary,
        kind=kind,
        steps=tuple(steps),
        dependencies=tuple(deps),
        required_capabilities=tuple(capabilities),
        risk_level=risk,
        risk_reason=risk_reason,
        estimated_cost=round(cost, 3),
        estimated_duration_s=round(duration, 1),
        requires_owner_approval=requires_approval,
        status=status,
        request_id=ctx.request_id,
        executable=False,
    )


def plan_from_dict_patch(existing: Plan, patch: dict[str, Any]) -> Plan:
    """Immutable update helper for PLAN_UPDATED — still non-executable."""
    kind = PlanKind(patch["kind"]) if "kind" in patch else existing.kind
    risk = PlanRiskLevel(patch["risk_level"]) if "risk_level" in patch else existing.risk_level
    status = PlanStatus(patch["status"]) if "status" in patch else existing.status
    caps = (
        tuple(patch["required_capabilities"])
        if "required_capabilities" in patch
        else existing.required_capabilities
    )
    return Plan(
        plan_id=existing.plan_id,
        goal=str(patch.get("goal", existing.goal)),
        summary=str(patch.get("summary", existing.summary)),
        kind=kind,
        steps=existing.steps,
        dependencies=existing.dependencies,
        required_capabilities=caps,
        risk_level=risk,
        risk_reason=str(patch.get("risk_reason", existing.risk_reason)),
        estimated_cost=float(patch.get("estimated_cost", existing.estimated_cost)),
        estimated_duration_s=float(
            patch.get("estimated_duration", patch.get("estimated_duration_s", existing.estimated_duration_s))
        ),
        requires_owner_approval=bool(
            patch.get("requires_owner_approval", existing.requires_owner_approval)
        ),
        status=status,
        request_id=existing.request_id,
        created_at=existing.created_at,
        executable=False,
    )
