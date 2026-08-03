"""Command pipeline — every stage runs; none may be skipped."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..identity import IdentityService
from ..memory import MemoryEngine, MemoryKind
from .audit_hooks import AuditJournal
from .capabilities import CapabilityRegistry
from .dispatcher import CapabilityDispatcher, DispatchResult
from .intent import IntentEngine
from .normalize import normalize_command
from .policy import PolicyDecision, PolicyDecisionKind, PolicyEngine
from .types import CommandEnvelope, ExecutionPlan, Intent, NormalizedCommand, RiskLevel


PIPELINE_STAGES: tuple[str, ...] = (
    "input",
    "normalize",
    "identity",
    "memory_context",
    "intent_detection",
    "policy_check",
    "capability_lookup",
    "execution_plan",
    "dispatch",
    "audit",
    "response",
)


@dataclass
class PipelineResult:
    command_id: str
    enabled: bool
    stages_completed: list[str] = field(default_factory=list)
    normalized: NormalizedCommand | None = None
    identity_context: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    intent: Intent | None = None
    policy: PolicyDecision | None = None
    missing_capabilities: list[str] = field(default_factory=list)
    plan: ExecutionPlan | None = None
    dispatch_results: list[DispatchResult] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "enabled": self.enabled,
            "stages_completed": list(self.stages_completed),
            "pipeline_complete": self.stages_completed == list(PIPELINE_STAGES),
            "identity_context": dict(self.identity_context),
            "memory_context": dict(self.memory_context),
            "intent": None if self.intent is None else self.intent.to_public_dict(),
            "policy": None
            if self.policy is None
            else {"kind": self.policy.kind.value, "reason": self.policy.reason},
            "missing_capabilities": list(self.missing_capabilities),
            "plan": None if self.plan is None else self.plan.to_public_dict(),
            "dispatch_results": [
                {"ok": d.ok, "capability": d.capability, "result": d.result, "error": d.error}
                for d in self.dispatch_results
            ],
            "response": dict(self.response),
            "error": self.error,
        }


class CommandPipeline:
    def __init__(
        self,
        *,
        intent_engine: IntentEngine,
        policy_engine: PolicyEngine,
        registry: CapabilityRegistry,
        dispatcher: CapabilityDispatcher,
        audit: AuditJournal,
        identity: IdentityService | None = None,
        memory: MemoryEngine | None = None,
    ) -> None:
        self._intent = intent_engine
        self._policy = policy_engine
        self._registry = registry
        self._dispatcher = dispatcher
        self._audit = audit
        self._identity = identity
        self._memory = memory

    def _ctx(
        self,
        *,
        owner_id: str | None = None,
        session_id: str | None = None,
        workspace_id: str | None = None,
        intent_id: str | None = None,
        source: str | None = None,
        risk_level: str | None = None,
    ) -> dict[str, Any]:
        return {
            "owner_id": owner_id,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "intent_id": intent_id,
            "source": source,
            "risk_level": risk_level,
        }

    def run(self, envelope: CommandEnvelope, *, enabled: bool) -> PipelineResult:
        started = time.perf_counter()
        command_id = f"cmd_{uuid.uuid4().hex}"
        result = PipelineResult(command_id=command_id, enabled=enabled)
        result.stages_completed.append("input")

        source = envelope.source.value
        owner_id: str | None = None
        session_id: str | None = None
        workspace_id: str | None = None
        intent_id: str | None = None

        self._audit.emit(
            AuditJournal.REQUEST_RECEIVED,
            command_id,
            source=source,
            status="received",
            metadata={"text_len": len(envelope.text or "")},
        )

        try:
            # normalize
            result.normalized = normalize_command(envelope)
            result.stages_completed.append("normalize")
            self._audit.emit(
                AuditJournal.REQUEST_NORMALIZED,
                command_id,
                source=source,
                status="normalized",
                metadata={"normalized_len": len(result.normalized.text)},
            )

            if not enabled:
                result.identity_context = {"enabled": False}
                result.stages_completed.append("identity")
                self._audit.emit(AuditJournal.IDENTITY_RESOLVED, command_id, source=source, status="skipped")
                result.memory_context = {"enabled": False}
                result.stages_completed.append("memory_context")
                self._audit.emit(AuditJournal.MEMORY_RESOLVED, command_id, source=source, status="skipped")
                result.intent = self._intent.detect(
                    result.normalized, owner_id=None, workspace_id=None, session_id=None
                )
                intent_id = result.intent.intent_id
                result.stages_completed.append("intent_detection")
                self._audit.emit(
                    AuditJournal.INTENT_CLASSIFIED,
                    command_id,
                    source=source,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="classified",
                    metadata={"type": result.intent.type},
                )
                result.policy = PolicyDecision(PolicyDecisionKind.DENIED, "gateway disabled")
                result.stages_completed.append("policy_check")
                self._audit.emit(
                    AuditJournal.POLICY_EVALUATED,
                    command_id,
                    source=source,
                    intent_id=intent_id,
                    status=result.policy.kind.value,
                    metadata={"reason": result.policy.reason},
                )
                result.missing_capabilities = []
                result.stages_completed.append("capability_lookup")
                result.plan = ExecutionPlan(
                    plan_id=f"plan_{uuid.uuid4().hex}",
                    intent_id=result.intent.intent_id,
                    capabilities=(),
                    risk_level=RiskLevel.FORBIDDEN,
                    blocked_reason="gateway disabled",
                )
                result.stages_completed.append("execution_plan")
                self._audit.emit(
                    AuditJournal.PLAN_CREATED,
                    command_id,
                    source=source,
                    intent_id=intent_id,
                    status="blocked",
                    metadata={"blocked_reason": "gateway disabled"},
                )
                result.dispatch_results = []
                result.stages_completed.append("dispatch")
                dur = (time.perf_counter() - started) * 1000.0
                self._audit.emit(
                    AuditJournal.REQUEST_FAILED,
                    command_id,
                    source=source,
                    intent_id=intent_id,
                    status="failed",
                    duration_ms=dur,
                    metadata={"reason": "gateway disabled"},
                )
                result.stages_completed.append("audit")
                result.response = {"ok": False, "reason": "gateway disabled"}
                result.stages_completed.append("response")
                return result

            # identity
            runtime_safe = False
            runtime_estop = False
            identity_enabled = False
            if self._identity is not None:
                identity_enabled = self._identity.enabled
                snap = self._identity.snapshot()
                if snap.owner is not None:
                    owner_id = snap.owner.owner_id
                if snap.session is not None:
                    session_id = snap.session.session_id
                if snap.workspace is not None:
                    workspace_id = snap.workspace.workspace_id
                if snap.runtime is not None:
                    runtime_safe = bool(snap.runtime.safe_mode)
                    runtime_estop = bool(snap.runtime.e_stop)
                result.identity_context = {
                    "enabled": snap.enabled,
                    "owner_id": owner_id,
                    "session_id": session_id,
                    "workspace_id": workspace_id,
                    "safe_mode": runtime_safe,
                    "e_stop": runtime_estop,
                }
            else:
                result.identity_context = {"enabled": False, "bound": False}
            result.stages_completed.append("identity")
            self._audit.emit(
                AuditJournal.IDENTITY_RESOLVED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                status="resolved",
                metadata={"identity_enabled": identity_enabled},
            )

            # memory
            if self._memory is not None and self._memory.enabled:
                mem_snap = self._memory.snapshot()
                result.memory_context = {
                    "enabled": True,
                    "revision": mem_snap.get("revision"),
                    "record_count": mem_snap.get("record_count"),
                    "task_count": len(self._memory.list(MemoryKind.TASK)),
                }
            else:
                result.memory_context = {"enabled": False}
            result.stages_completed.append("memory_context")
            self._audit.emit(
                AuditJournal.MEMORY_RESOLVED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                status="resolved",
                metadata=dict(result.memory_context),
            )

            # intent
            result.intent = self._intent.detect(
                result.normalized,
                owner_id=owner_id,
                workspace_id=workspace_id,
                session_id=session_id,
            )
            intent_id = result.intent.intent_id
            result.stages_completed.append("intent_detection")
            self._audit.emit(
                AuditJournal.INTENT_CLASSIFIED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                intent_id=intent_id,
                risk_level=result.intent.risk_level.value,
                status="classified",
                metadata={"type": result.intent.type, "confidence": result.intent.confidence},
            )

            # policy
            result.policy = self._policy.evaluate(
                result.intent,
                safe_mode=runtime_safe,
                e_stop=runtime_estop,
                identity_enabled=identity_enabled,
                has_owner=owner_id is not None,
            )
            result.stages_completed.append("policy_check")
            self._audit.emit(
                AuditJournal.POLICY_EVALUATED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                intent_id=intent_id,
                risk_level=result.intent.risk_level.value,
                status=result.policy.kind.value,
                metadata={"reason": result.policy.reason},
            )
            if result.policy.kind == PolicyDecisionKind.BLOCKED_SAFE_MODE:
                self._audit.emit(
                    AuditJournal.SAFE_MODE_BLOCK,
                    command_id,
                    source=source,
                    owner_id=owner_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="blocked",
                )
            if result.policy.kind == PolicyDecisionKind.BLOCKED_E_STOP:
                self._audit.emit(
                    AuditJournal.ESTOP_BLOCK,
                    command_id,
                    source=source,
                    owner_id=owner_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="blocked",
                )

            # capability lookup
            missing = [c for c in result.intent.required_capabilities if not self._registry.has(c)]
            result.missing_capabilities = missing
            result.stages_completed.append("capability_lookup")

            # plan
            requires_approval = result.policy.kind == PolicyDecisionKind.NEEDS_APPROVAL
            requires_confirmation = result.policy.kind == PolicyDecisionKind.NEEDS_CONFIRMATION
            blocked = result.policy.kind in {
                PolicyDecisionKind.DENIED,
                PolicyDecisionKind.BLOCKED_SAFE_MODE,
                PolicyDecisionKind.BLOCKED_E_STOP,
            } or bool(missing)
            caps = () if blocked or requires_approval or requires_confirmation else tuple(
                result.intent.required_capabilities
            )
            result.plan = ExecutionPlan(
                plan_id=f"plan_{uuid.uuid4().hex}",
                intent_id=result.intent.intent_id,
                capabilities=caps,
                risk_level=result.intent.risk_level,
                requires_approval=requires_approval,
                requires_confirmation=requires_confirmation,
                blocked_reason=(
                    result.policy.reason
                    if blocked
                    else ("missing capabilities: " + ",".join(missing) if missing else None)
                ),
            )
            result.stages_completed.append("execution_plan")
            self._audit.emit(
                AuditJournal.PLAN_CREATED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                intent_id=intent_id,
                risk_level=result.intent.risk_level.value,
                status="planned",
                metadata=result.plan.to_public_dict(),
            )

            # dispatch
            if result.policy.may_dispatch and result.plan.capabilities and not missing:
                self._audit.emit(
                    AuditJournal.DISPATCH_STARTED,
                    command_id,
                    source=source,
                    owner_id=owner_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="started",
                    capability=",".join(result.plan.capabilities),
                )
                result.dispatch_results = self._dispatcher.dispatch(result.intent, result.plan)
                ok = all(d.ok for d in result.dispatch_results)
                self._audit.emit(
                    AuditJournal.DISPATCH_COMPLETED,
                    command_id,
                    source=source,
                    owner_id=owner_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="ok" if ok else "failed",
                    capability=",".join(result.plan.capabilities),
                    result={"items": [{"ok": d.ok, "capability": d.capability} for d in result.dispatch_results]},
                )
                dur = (time.perf_counter() - started) * 1000.0
                if ok:
                    self._audit.emit(
                        AuditJournal.REQUEST_COMPLETED,
                        command_id,
                        source=source,
                        owner_id=owner_id,
                        session_id=session_id,
                        workspace_id=workspace_id,
                        intent_id=intent_id,
                        risk_level=result.intent.risk_level.value,
                        status="completed",
                        duration_ms=dur,
                        capability=",".join(result.plan.capabilities),
                    )
                    result.response = {
                        "ok": True,
                        "intent": result.intent.type,
                        "dispatch": [d.result for d in result.dispatch_results],
                    }
                else:
                    self._audit.emit(
                        AuditJournal.REQUEST_FAILED,
                        command_id,
                        source=source,
                        owner_id=owner_id,
                        session_id=session_id,
                        workspace_id=workspace_id,
                        intent_id=intent_id,
                        status="failed",
                        duration_ms=dur,
                        metadata={"reason": "dispatch failed"},
                    )
                    result.response = {"ok": False, "reason": "dispatch failed"}
            else:
                dur = (time.perf_counter() - started) * 1000.0
                self._audit.emit(
                    AuditJournal.REQUEST_FAILED,
                    command_id,
                    source=source,
                    owner_id=owner_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    risk_level=result.intent.risk_level.value,
                    status="failed",
                    duration_ms=dur,
                    metadata={
                        "policy": result.policy.kind.value,
                        "reason": result.policy.reason,
                    },
                )
                result.response = {
                    "ok": False,
                    "policy": result.policy.kind.value,
                    "reason": result.policy.reason,
                    "requires_approval": requires_approval,
                    "requires_confirmation": requires_confirmation,
                }
            result.stages_completed.append("dispatch")
            result.stages_completed.append("audit")
            result.stages_completed.append("response")
            return result

        except Exception as exc:  # pragma: no cover
            result.error = str(exc)
            self._audit.emit(
                AuditJournal.REQUEST_FAILED,
                command_id,
                source=source,
                owner_id=owner_id,
                session_id=session_id,
                workspace_id=workspace_id,
                intent_id=intent_id,
                status="failed",
                metadata={"error": str(exc)},
            )
            for stage in PIPELINE_STAGES:
                if stage not in result.stages_completed:
                    result.stages_completed.append(stage)
            result.response = {"ok": False, "error": str(exc)}
            return result
