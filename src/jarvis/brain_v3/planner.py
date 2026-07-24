"""Non-executable planner service for Brain V3 Phase 1."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from .errors import LimitExceededError, NotFoundError, ValidationError
from .limits import BrainV3Limits
from .models import Plan, PlanStep, new_id, utc_now_iso
from .validation import build_plan


class PlannerService:
    """Creates and manages plans without executing any step."""

    def __init__(self, repo: Any, limits: BrainV3Limits | None = None) -> None:
        self._repo = repo
        self._limits = limits or BrainV3Limits()

    def _ensure_writable(self) -> None:
        if getattr(self._repo, "read_only", False):
            raise ValidationError("repository is read-only")

    def create_plan(
        self,
        goal_entity_id: Optional[str],
        title: str,
        step_titles: List[str],
        **meta: Any,
    ) -> Plan:
        """Create a plan whose steps are always non-executable."""
        self._ensure_writable()
        if self._repo.count_plans() >= self._limits.max_plans:
            raise LimitExceededError("max_plans exceeded")
        if len(step_titles) > self._limits.max_plan_steps:
            raise LimitExceededError("max_plan_steps exceeded")
        if goal_entity_id is not None:
            self._repo.get_entity(goal_entity_id)

        plan_id = new_id("plan")
        steps = [
            PlanStep(
                id=new_id("step"),
                plan_id=plan_id,
                order_index=index,
                title=str(step_title),
                description="",
                status="pending",
                dependencies=[],
                risk_level="low",
                requires_approval=True,
                execution_forbidden=True,
            )
            for index, step_title in enumerate(step_titles)
        ]
        payload = {
            "id": plan_id,
            "goal_entity_id": goal_entity_id,
            "title": title,
            "status": "draft",
            "steps": [step.to_dict() for step in steps],
            "assumptions": list(meta.get("assumptions") or []),
            "constraints": list(meta.get("constraints") or []),
            "risks": list(meta.get("risks") or []),
            "approval_points": list(meta.get("approval_points") or []),
            "verification_steps": list(meta.get("verification_steps") or []),
            "rollback_notes": list(meta.get("rollback_notes") or []),
            "source_id": meta.get("source_id"),
            "confidence": meta.get("confidence", 0.5),
        }
        plan = build_plan(payload, self._limits)
        for step in plan.steps:
            step.requires_approval = True
            step.execution_forbidden = True
        return self._repo.create_plan(plan)

    def get_plan(self, plan_id: str) -> Plan:
        return self._repo.get_plan(plan_id)

    def update_plan_status(self, plan_id: str, status: str) -> Plan:
        self._ensure_writable()
        plan = self.get_plan(plan_id)
        updated = build_plan({**plan.to_dict(), "status": status, "updated_at": utc_now_iso()}, self._limits)
        return self._repo.update_plan(updated)

    def reorder_steps(self, plan_id: str, step_ids: List[str]) -> Plan:
        self._ensure_writable()
        plan = self.get_plan(plan_id)
        by_id = {step.id: step for step in plan.steps}
        if set(step_ids) != set(by_id):
            raise ValidationError("step_ids must match plan steps exactly")
        reordered: List[PlanStep] = []
        for index, step_id in enumerate(step_ids):
            step = by_id[step_id]
            step.order_index = index
            step.requires_approval = True
            step.execution_forbidden = True
            reordered.append(step)
        plan.steps = reordered
        plan.updated_at = utc_now_iso()
        updated = self._repo.update_plan(plan)
        for step in reordered:
            self._repo.update_plan_step(step)
        return self.get_plan(plan_id)

    def mark_step_blocked(self, plan_id: str, step_id: str, *, reason: str = "") -> Plan:
        self._ensure_writable()
        plan = self.get_plan(plan_id)
        found = False
        for step in plan.steps:
            if step.id == step_id:
                step.status = "blocked"
                if reason:
                    step.description = reason
                step.requires_approval = True
                step.execution_forbidden = True
                found = True
                break
        if not found:
            raise NotFoundError(f"plan step not found: {step_id}")
        if plan.status != "archived":
            plan.status = "blocked"
        plan.updated_at = utc_now_iso()
        self._repo.update_plan(plan)
        for step in plan.steps:
            if step.id == step_id:
                self._repo.update_plan_step(step)
                break
        return self.get_plan(plan_id)

    def archive_plan(self, plan_id: str) -> Plan:
        return self.update_plan_status(plan_id, "archived")

    def update_plan_metadata(self, plan_id: str, updates: Mapping[str, Any]) -> Plan:
        """Optional helper for manual metadata edits without execution."""
        self._ensure_writable()
        plan = self.get_plan(plan_id)
        merged = {**plan.to_dict(), **dict(updates), "id": plan_id, "updated_at": utc_now_iso()}
        updated = build_plan(merged, self._limits)
        for step in updated.steps:
            step.requires_approval = True
            step.execution_forbidden = True
        return self._repo.update_plan(updated)
