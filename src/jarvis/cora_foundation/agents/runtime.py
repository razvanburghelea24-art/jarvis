"""AgentRuntime — run one task → AgentResult. No Dispatcher. No Orchestrator yet.

Phase 5.5 will add Agent Orchestrator / Scheduler on top of this runtime.
"""

from __future__ import annotations

import threading
from typing import Any

from ..audit import AuditEngine, AuditEventType
from .flags import agents_enabled_from_env
from .registry import AgentRegistry, default_agent_registry
from .task_graph import TaskGraph, TaskNode, TaskStatus
from .types import AgentResult, AgentResultStatus

_SCHEMA = "cora.agents.runtime.v1"


class AgentRuntime:
    """
    Thin runner for specialist agents.

    Golden rules:
    - Agents return AgentResult only
    - Never call Dispatcher / live APIs / Memory.write / file write
    - Never take final Owner decisions
    - Planner remains the boss (runtime does not re-plan)
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        registry: AgentRegistry | None = None,
        audit: AuditEngine | None = None,
    ) -> None:
        self._enabled = agents_enabled_from_env() if enabled is None else bool(enabled)
        self._registry = registry or default_agent_registry()
        self._audit = audit
        self._lock = threading.RLock()
        self._results: dict[str, AgentResult] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def get_result(self, result_id: str) -> AgentResult | None:
        with self._lock:
            return self._results.get(result_id)

    def list_results(self) -> list[AgentResult]:
        with self._lock:
            return list(self._results.values())

    def run_task(
        self,
        task: TaskNode,
        *,
        context: dict[str, Any] | None = None,
        graph: TaskGraph | None = None,
    ) -> AgentResult | None:
        """Execute one specialist task → AgentResult. None when module OFF."""
        if not self._enabled:
            return None

        agent = self._registry.get(task.agent_role)
        if agent is None:
            result = AgentResult(
                result_id=f"ares_missing_{task.task_id}",
                agent_role=task.agent_role,
                task_id=task.task_id,
                plan_id=task.plan_id,
                status=AgentResultStatus.FAILED,
                summary=f"No agent registered for role {task.agent_role.value}",
                confidence=0.0,
            )
            self._store(result, graph, task, failed=True)
            return result

        if graph is not None:
            graph.mark_running(task.task_id)

        self._audit_event(
            AuditEventType.AGENT_TASK_STARTED,
            task=task,
            status="started",
        )

        # Attach prior results for Review/Validation confidence chaining.
        ctx = dict(context or {})
        with self._lock:
            ctx.setdefault(
                "prior_results",
                [r.to_public_dict() for r in self._results.values()],
            )

        result = agent.run(task, context=ctx)
        # Enforce invariants even if a specialist misbehaves later.
        assert result.dispatches is False
        assert result.decides_architecture is False
        assert result.final_decision is False

        failed = result.status == AgentResultStatus.FAILED
        self._store(result, graph, task, failed=failed)
        self._audit_event(
            AuditEventType.AGENT_TASK_COMPLETED if not failed else AuditEventType.AGENT_TASK_FAILED,
            task=task,
            status=result.status.value,
            result=result,
        )
        return result

    def run_ready(self, graph: TaskGraph, *, context: dict[str, Any] | None = None) -> list[AgentResult]:
        """
        Run all currently READY tasks (parallel-eligible set) sequentially in-process.
        True parallelism / scheduling lands in Phase 5.5 Orchestrator.
        """
        if not self._enabled:
            return []
        out: list[AgentResult] = []
        for task in list(graph.ready_tasks()):
            r = self.run_task(task, context=context, graph=graph)
            if r is not None:
                out.append(r)
        return out

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "schema": _SCHEMA,
                "dispatches": False,
                "decides_architecture": False,
                "final_decision": False,
                "orchestrator": False,  # Phase 5.5
                "roles": [r.value for r in self._registry.roles()],
                "result_count": len(self._results),
            }

    def _store(
        self,
        result: AgentResult,
        graph: TaskGraph | None,
        task: TaskNode,
        *,
        failed: bool,
    ) -> None:
        with self._lock:
            self._results[result.result_id] = result
        if graph is not None:
            if failed:
                graph.mark_failed(task.task_id, result_id=result.result_id)
            else:
                graph.mark_completed(task.task_id, result_id=result.result_id)

    def _audit_event(
        self,
        event_type: AuditEventType,
        *,
        task: TaskNode,
        status: str,
        result: AgentResult | None = None,
    ) -> None:
        if self._audit is None or not self._audit.enabled:
            return
        meta: dict[str, Any] = {
            "agent_role": task.agent_role.value,
            "task_id": task.task_id,
            "plan_id": task.plan_id,
        }
        if result is not None:
            meta.update(
                {
                    "result_id": result.result_id,
                    "confidence": result.confidence,
                    "quality": result.quality.to_public_dict(),
                    "recommends_review": result.recommends_review,
                }
            )
        self._audit.append(
            event_type=event_type,
            request_id=task.plan_id or task.task_id,
            status=status,
            capability=task.capability,
            result={
                "dispatches": False,
                "final_decision": False,
            },
            metadata=meta,
        )


_RUNTIME: AgentRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_agent_runtime(
    *,
    enabled: bool | None = None,
    audit: AuditEngine | None = None,
) -> AgentRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = AgentRuntime(enabled=enabled, audit=audit)
        else:
            if enabled is not None:
                _RUNTIME.set_enabled(bool(enabled))
        return _RUNTIME


def reset_agent_runtime_for_tests() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
