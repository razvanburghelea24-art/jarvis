"""PlannerRouter — ConversationDecision → PlannerDecision (deterministic v1).

Never executes · never builds TaskGraph · never calls LLM · Tools · Gateway · Electron.
Law: Everything that changes the world must first become a PlannerDecision.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..conversation.contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
)
from ..workspace import WorkspaceEngine
from .routing_decision import (
    PlannerDecision,
    PlannerRisk,
    PlannerRoute,
)

# Multi-step / planning triggers (RO + EN) — avoid \\b after diacritics
_PLAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(construie[sș]te|build|implement|refactor|deploy|migrate)", re.I),
    re.compile(r"(analizeaz[ăa]|analyze|analyse).{0,48}(proiect|project|repo|codebase)", re.I),
    re.compile(r"(compar[ăa]|compare).{0,40}(\d+|cinci|five|mai multe|several|variante|options)", re.I),
    re.compile(r"(f[ăa]\s+un\s+plan|make\s+a\s+plan|create\s+a\s+plan|planific[ăa])", re.I),
    re.compile(r"(pas\s*cu\s*pas|step\s*by\s*step|multi[\s-]?step|pa[sș]i\s+multipli)", re.I),
    re.compile(r"(release|ship|roll\s*out|rollback)", re.I),
    # World-changing intents must become PlannerDecision first
    re.compile(r"(creeaz[ăa]|create).{0,40}(pr|pull\s*request|github)", re.I),
    re.compile(r"(trimite|send).{0,40}discord", re.I),
    re.compile(r"(github|discord|railway).{0,20}(pr|deploy|mesaj|message|anun)", re.I),
    re.compile(r"(n8n|workflow).{0,40}(ruleaz[ăa]|execute|run|trigger)", re.I),
    re.compile(r"(ruleaz[ăa]|execute|run).{0,40}(n8n|workflow)", re.I),
)

_DIRECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(ce\s+este|what\s+is|cine\s+este|who\s+is|cum\s+se\s+nume[sș]te)\b", re.I),
    re.compile(r"\b(explic[ăa]|explain|define[sș]te|define|meaning\s+of)\b", re.I),
    re.compile(r"^\s*(salut|hello|hi|hey|bun[ăa]|status|ping)\s*[!.?]?\s*$", re.I),
)

_CAP_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(github|pr|pull\s*request)\b", re.I), "github"),
    (re.compile(r"\bdiscord\b", re.I), "discord"),
    (re.compile(r"\b(deploy|railway)\b", re.I), "deploy"),
    (re.compile(r"\b(n8n|workflow)\b", re.I), "n8n"),
    (re.compile(r"\b(file|fi[sș]ier|edit|modific[ăa])\b", re.I), "filesystem"),
    (re.compile(r"\b(computer|desktop|mouse|keyboard|operator)\b", re.I), "computer_operator"),
    (re.compile(r"\b(analyz|analiz)\b", re.I), "analysis"),
    (re.compile(r"\b(build|constru|implement)\b", re.I), "implementation"),
)


class PlannerRouter:
    """Deterministic planner routing only."""

    def route(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
        *,
        workspace: WorkspaceEngine | None = None,
    ) -> PlannerDecision:
        label = str(decision.tool_intent.get("label") or decision.kind.value)
        text = (request.input or "").strip()

        # Clarify / refuse → never plan
        if label in {"AskClarification", "NeedsReview", "Refuse"} or decision.kind.value in {
            "clarify",
            "refuse",
        }:
            return self._direct(
                request,
                reason=f"decision_{label}_no_plan",
                metadata={"decision_label": label},
            )

        # Existing plan on active workspace
        if workspace is not None:
            active = workspace.get_context(request.session_id)
            if active and active.active_plan:
                return PlannerDecision(
                    decision_id=PlannerDecision.new_id(),
                    request_id=request.request_id,
                    required=True,
                    reason="existing_active_plan",
                    route=PlannerRoute.EXISTING_PLAN,
                    priority=3,
                    estimated_steps=max(1, len(active.active_tasks) or 1),
                    estimated_duration_sec=60.0 * max(1, len(active.active_tasks) or 1),
                    estimated_cost=0.2,
                    risk=PlannerRisk.LOW,
                    required_capabilities=("plan.resume",),
                    approval_required=False,
                    metadata={
                        "active_plan": active.active_plan,
                        "workspace_id": active.workspace_id,
                    },
                )

        if self._is_direct(text):
            return self._direct(request, reason="simple_or_explanatory", metadata={"matched": "direct"})

        if self._needs_plan(text):
            caps = self._capabilities(text)
            steps = self._estimate_steps(text)
            risk = self._estimate_risk(caps, text)
            return PlannerDecision(
                decision_id=PlannerDecision.new_id(),
                request_id=request.request_id,
                required=True,
                reason="multi_step_or_plan_request",
                route=PlannerRoute.CREATE_PLAN,
                priority=2 if risk in {PlannerRisk.HIGH, PlannerRisk.CRITICAL} else 4,
                estimated_steps=steps,
                estimated_duration_sec=float(30 * steps),
                estimated_cost=round(0.15 * steps, 3),
                risk=risk,
                required_capabilities=caps,
                approval_required=risk in {PlannerRisk.HIGH, PlannerRisk.CRITICAL} or bool(caps),
                metadata={
                    "decision_label": label,
                    "workspace_id": context.workspace_id,
                    "world_change_gate": True,
                },
            )

        return self._direct(request, reason="default_direct_response", metadata={"decision_label": label})

    def _direct(
        self,
        request: ConversationRequest,
        *,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> PlannerDecision:
        return PlannerDecision(
            decision_id=PlannerDecision.new_id(),
            request_id=request.request_id,
            required=False,
            reason=reason,
            route=PlannerRoute.DIRECT_RESPONSE,
            priority=8,
            estimated_steps=0,
            estimated_duration_sec=0.0,
            estimated_cost=0.0,
            risk=PlannerRisk.NONE,
            required_capabilities=(),
            approval_required=False,
            metadata=dict(metadata or {}),
        )

    def _is_direct(self, text: str) -> bool:
        if not text or len(text) < 3:
            return True
        return any(p.search(text) for p in _DIRECT_PATTERNS)

    def _needs_plan(self, text: str) -> bool:
        return any(p.search(text) for p in _PLAN_PATTERNS)

    def _capabilities(self, text: str) -> tuple[str, ...]:
        found: list[str] = []
        for pat, cap in _CAP_HINTS:
            if pat.search(text) and cap not in found:
                found.append(cap)
        if not found:
            found.append("planning")
        return tuple(found)

    def _estimate_steps(self, text: str) -> int:
        n = 3
        if re.search(r"\b(\d+)\b", text):
            m = re.search(r"\b(\d+)\b", text)
            if m:
                n = max(n, min(12, int(m.group(1))))
        if re.search(r"\b(compar|compare)\b", text, re.I):
            n = max(n, 5)
        if re.search(r"\b(deploy|release|migrat)\b", text, re.I):
            n = max(n, 6)
        return n

    def _estimate_risk(self, caps: tuple[str, ...], text: str) -> PlannerRisk:
        if any(c in caps for c in ("deploy", "computer_operator", "github")):
            return PlannerRisk.HIGH
        if "discord" in caps or "filesystem" in caps:
            return PlannerRisk.MEDIUM
        if re.search(r"\b(delete|șterge|sterge|destroy|drop)\b", text, re.I):
            return PlannerRisk.CRITICAL
        return PlannerRisk.LOW
