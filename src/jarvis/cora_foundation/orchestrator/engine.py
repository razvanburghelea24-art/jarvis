"""Agent Orchestrator / Scheduler — schedule TaskGraph waves. Never invent tasks."""

from __future__ import annotations

import threading
from typing import Any

from ..agents.runtime import AgentRuntime
from ..agents.task_graph import TaskGraph, TaskNode, TaskStatus
from ..agents.types import AgentResult, AgentResultStatus, AgentRole
from ..audit import AuditEngine, AuditEventType
from .config import OrchestratorConfig, ResourceHint
from .flags import orchestrator_enabled_from_env
from .observe import GraphProgress, snapshot_progress

_SCHEMA = "cora.orchestrator.v1"
_CONFIDENCE_BLOCK = "confidence_gate"


class AgentOrchestrator:
    """
    Scheduler rules:
    1. Receives TaskGraph only — never creates tasks
    2. Does not call Dispatcher / live APIs
    3. Parallel READY waves
    4. Confidence gating (configurable)
    5. Retry policy
    6. Owner approval gates
    7. Resource hints (agents unaware of provider choice)
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        config: OrchestratorConfig | None = None,
        audit: AuditEngine | None = None,
        runtime: AgentRuntime | None = None,
    ) -> None:
        self._enabled = orchestrator_enabled_from_env() if enabled is None else bool(enabled)
        self._config = config or OrchestratorConfig()
        self._audit = audit
        self._runtime = runtime  # optional delegate for specialist runs only
        self._lock = threading.RLock()
        self._graph: TaskGraph | None = None
        self._last_confidence: dict[str, float] = {}  # task_id → confidence
        self._role_confidence: dict[str, float] = {}  # role → last confidence

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def schema_version(self) -> str:
        return _SCHEMA

    def config(self) -> OrchestratorConfig:
        return self._config

    def bind_graph(self, graph: TaskGraph) -> None:
        """Accept Planner-built TaskGraph. Refuses to add nodes."""
        if not self._enabled:
            return
        if not isinstance(graph, TaskGraph):
            raise TypeError("bind_graph requires TaskGraph from Planner/agents")
        graph.validate()
        with self._lock:
            self._graph = graph
            self._last_confidence.clear()
            self._role_confidence.clear()
            # Apply default retry policy onto nodes that still use defaults
            for node in graph.nodes():
                if node.max_retry == 2 and self._config.default_max_retry != 2:
                    node.max_retry = self._config.default_max_retry
                if node.requires_owner_approval is False:
                    if node.agent_role.value in self._config.approval_roles:
                        node.requires_owner_approval = True
                    if node.capability and node.capability in self._config.approval_capabilities:
                        node.requires_owner_approval = True
        self.sync_states()

    def graph(self) -> TaskGraph | None:
        return self._graph

    def invent_task(self, *_args: Any, **_kwargs: Any) -> None:
        """Hard fail — Scheduler must never create tasks."""
        raise RuntimeError("Orchestrator must not invent tasks — Planner owns TaskGraph")

    def add_task(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Orchestrator must not invent tasks — Planner owns TaskGraph")

    def sync_states(self) -> list[str]:
        """
        Recompute WAITING / READY / BLOCKED from deps, confidence, approval.
        Returns newly READY task ids (audited).
        """
        if not self._enabled or self._graph is None:
            return []
        newly_ready: list[str] = []
        with self._lock:
            g = self._graph
            for node in g.nodes():
                if node.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.RUNNING,
                    TaskStatus.SKIPPED,
                    TaskStatus.FAILED,
                }:
                    continue

                if not self._deps_ok_for(node):
                    if node.status == TaskStatus.READY:
                        node.status = TaskStatus.PENDING
                    continue

                # Confidence gate on this node based on upstream confidences
                if self._confidence_blocks(node):
                    if node.status != TaskStatus.BLOCKED or node.blocked_reason != _CONFIDENCE_BLOCK:
                        node.status = TaskStatus.BLOCKED
                        node.blocked_reason = _CONFIDENCE_BLOCK
                        self._emit_audit(
                            AuditEventType.TASK_BLOCKED,
                            node,
                            status="blocked",
                            metadata={"reason": _CONFIDENCE_BLOCK},
                        )
                    continue

                # Approval gate
                if node.requires_owner_approval and not node.owner_approved:
                    if node.status != TaskStatus.WAITING:
                        node.status = TaskStatus.WAITING
                        node.blocked_reason = "owner_approval"
                        self._emit_audit(
                            AuditEventType.TASK_BLOCKED,
                            node,
                            status="waiting_approval",
                            metadata={"reason": "owner_approval"},
                        )
                    continue

                prev = node.status
                node.status = TaskStatus.READY
                node.blocked_reason = None
                if prev != TaskStatus.READY:
                    newly_ready.append(node.task_id)
                    self._emit_audit(AuditEventType.TASK_READY, node, status="ready")
        return newly_ready

    def select_wave(self) -> list[TaskNode]:
        """Independent READY tasks — true parallel set."""
        if not self._enabled or self._graph is None:
            return []
        self.sync_states()
        with self._lock:
            return [n for n in self._graph.nodes() if n.status == TaskStatus.READY]

    def resource_hint(self, task: TaskNode) -> ResourceHint:
        return self._config.resource_for(task.agent_role)

    def mark_started(self, task_id: str) -> TaskNode | None:
        if not self._enabled or self._graph is None:
            return None
        with self._lock:
            node = self._graph.get(task_id)
            if node is None or node.status != TaskStatus.READY:
                return None
            node.status = TaskStatus.RUNNING
        self._emit_audit(AuditEventType.TASK_STARTED, node, status="started")
        return node

    def approve(self, task_id: str, *, owner_id: str) -> TaskNode | None:
        if not self._enabled or self._graph is None:
            return None
        if not owner_id:
            raise PermissionError("owner_id required for approval gate")
        with self._lock:
            node = self._graph.get(task_id)
            if node is None:
                return None
            node.owner_approved = True
            if node.status == TaskStatus.WAITING:
                node.status = TaskStatus.PENDING
                node.blocked_reason = None
        self.sync_states()
        return self._graph.get(task_id) if self._graph else None

    def report_result(self, task_id: str, result: AgentResult) -> TaskNode | None:
        """Ingest AgentResult — Scheduler does not run the agent itself here."""
        if not self._enabled or self._graph is None:
            return None
        with self._lock:
            node = self._graph.get(task_id)
            if node is None:
                return None
            self._last_confidence[task_id] = result.confidence
            self._role_confidence[node.agent_role.value] = result.confidence

            if result.status == AgentResultStatus.FAILED:
                return self._handle_failure(node, result)

            node.status = TaskStatus.COMPLETED
            node.result_id = result.result_id
            node.failure_reason = None
        self._emit_audit(
            AuditEventType.TASK_COMPLETED,
            node,
            status="completed",
            metadata={"confidence": result.confidence, "result_id": result.result_id},
        )
        # Low confidence may block gated successors (not invent Review)
        if result.confidence < self._config.threshold_for(AgentRole.CODE) and node.agent_role == AgentRole.RESEARCH:
            self._block_gated_successors(node, result.confidence)
        # Review success can clear confidence blocks so Code may proceed (still may need Owner approval)
        if node.agent_role == AgentRole.REVIEW and result.status == AgentResultStatus.COMPLETED:
            self._clear_confidence_blocks()
        self.sync_states()
        self._maybe_graph_completed()
        return node

    def run_specialist_wave(
        self,
        *,
        context: dict[str, Any] | None = None,
    ) -> list[AgentResult]:
        """
        Delegate READY wave to AgentRuntime (specialists).

        This is NOT Dispatcher execution and NOT task invention.
        Scheduler still does not perform specialist work itself.
        """
        if not self._enabled or self._graph is None:
            return []
        if self._runtime is None or not self._runtime.enabled:
            raise RuntimeError("AgentRuntime required and enabled for run_specialist_wave")

        wave = self.select_wave()
        results: list[AgentResult] = []
        for node in wave:
            started = self.mark_started(node.task_id)
            if started is None:
                continue
            ctx = dict(context or {})
            ctx["resource_hint"] = self.resource_hint(node).value
            # Agents must not choose the model — hint is opaque metadata.
            result = self._runtime.run_task(started, context=ctx, graph=None)
            # runtime would mark graph if passed — we own graph state via report_result
            if result is None:
                continue
            # Undo runtime's lack of graph bind: keep orchestrator SSOT
            self.report_result(node.task_id, result)
            results.append(result)
        return results

    def progress(self) -> GraphProgress | None:
        if self._graph is None:
            return None
        return snapshot_progress(self._graph)

    def status(self) -> dict[str, Any]:
        prog = self.progress()
        return {
            "enabled": self._enabled,
            "schema": _SCHEMA,
            "invents_tasks": False,
            "dispatches_live": False,
            "graph_bound": self._graph is not None,
            "config": {
                "confidence_thresholds": dict(self._config.confidence_thresholds),
                "default_max_retry": self._config.default_max_retry,
                "approval_roles": list(self._config.approval_roles),
            },
            "progress": None if prog is None else prog.to_public_dict(),
        }

    # ── internals ────────────────────────────────────────────────────────

    def _deps_ok_for(self, node: TaskNode) -> bool:
        assert self._graph is not None
        for dep_id in node.depends_on:
            dep = self._graph.get(dep_id)
            if dep is None:
                return False
            if dep.status == TaskStatus.COMPLETED:
                continue
            # Review may proceed when upstream is confidence-blocked (needs review path)
            if (
                node.agent_role == AgentRole.REVIEW
                and dep.status == TaskStatus.BLOCKED
                and dep.blocked_reason == _CONFIDENCE_BLOCK
            ):
                continue
            return False
        return True

    def _confidence_blocks(self, node: TaskNode) -> bool:
        """Block node if any completed upstream confidence is below role threshold."""
        threshold = self._config.threshold_for(node.agent_role)
        if threshold <= 0:
            return False
        assert self._graph is not None
        # Use min confidence among completed direct deps
        confs: list[float] = []
        for dep_id in node.depends_on:
            dep = self._graph.get(dep_id)
            if dep is None:
                continue
            if dep.status == TaskStatus.COMPLETED and dep_id in self._last_confidence:
                confs.append(self._last_confidence[dep_id])
        if not confs:
            return False
        return min(confs) < threshold

    def _block_gated_successors(self, source: TaskNode, confidence: float) -> None:
        assert self._graph is not None
        for node in self._graph.nodes():
            if source.task_id not in node.depends_on:
                continue
            if node.agent_role == AgentRole.REVIEW:
                continue  # review path stays available
            if node.status in {TaskStatus.COMPLETED, TaskStatus.RUNNING}:
                continue
            node.status = TaskStatus.BLOCKED
            node.blocked_reason = _CONFIDENCE_BLOCK
            self._emit_audit(
                AuditEventType.TASK_BLOCKED,
                node,
                status="blocked",
                metadata={
                    "reason": _CONFIDENCE_BLOCK,
                    "upstream_task": source.task_id,
                    "upstream_confidence": confidence,
                },
            )

    def _clear_confidence_blocks(self) -> None:
        assert self._graph is not None
        for node in self._graph.nodes():
            if node.status == TaskStatus.BLOCKED and node.blocked_reason == _CONFIDENCE_BLOCK:
                node.status = TaskStatus.PENDING
                node.blocked_reason = None

    def _handle_failure(self, node: TaskNode, result: AgentResult) -> TaskNode:
        node.failure_reason = result.summary
        node.result_id = result.result_id
        if node.retry_count < node.max_retry:
            node.retry_count += 1
            node.backoff_s = self._config.default_backoff_s * (
                self._config.backoff_multiplier ** (node.retry_count - 1)
            )
            node.status = TaskStatus.PENDING
            self._emit_audit(
                AuditEventType.TASK_RETRIED,
                node,
                status="retried",
                metadata={
                    "retry_count": node.retry_count,
                    "max_retry": node.max_retry,
                    "backoff_s": node.backoff_s,
                    "reason": node.failure_reason,
                },
            )
            self.sync_states()
            return node

        node.status = TaskStatus.FAILED
        self._emit_audit(
            AuditEventType.TASK_FAILED,
            node,
            status="failed",
            metadata={"reason": node.failure_reason, "retry_count": node.retry_count},
        )
        self._maybe_graph_completed()
        return node

    def _maybe_graph_completed(self) -> None:
        if self._graph is None:
            return
        nodes = self._graph.nodes()
        if not nodes:
            return
        if all(
            n.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED}
            for n in nodes
        ):
            self._emit_audit(
                AuditEventType.GRAPH_COMPLETED,
                nodes[0],
                status="graph_completed",
                metadata={
                    "graph_id": self._graph.graph_id,
                    "completed": sum(1 for n in nodes if n.status == TaskStatus.COMPLETED),
                    "failed": sum(1 for n in nodes if n.status == TaskStatus.FAILED),
                },
            )

    def _emit_audit(
        self,
        event_type: AuditEventType,
        node: TaskNode,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._audit is None or not self._audit.enabled:
            return
        self._audit.append(
            event_type=event_type,
            request_id=node.plan_id or (self._graph.graph_id if self._graph else node.task_id),
            status=status,
            capability=node.capability,
            source="orchestrator",
            result={"task_id": node.task_id, "agent_role": node.agent_role.value},
            metadata={
                "graph_id": None if self._graph is None else self._graph.graph_id,
                "resource_hint": self.resource_hint(node).value,
                **(metadata or {}),
            },
        )


_ORCH: AgentOrchestrator | None = None
_ORCH_LOCK = threading.Lock()


def get_orchestrator(
    *,
    enabled: bool | None = None,
    audit: AuditEngine | None = None,
    runtime: AgentRuntime | None = None,
    config: OrchestratorConfig | None = None,
) -> AgentOrchestrator:
    global _ORCH
    with _ORCH_LOCK:
        if _ORCH is None:
            _ORCH = AgentOrchestrator(
                enabled=enabled, audit=audit, runtime=runtime, config=config
            )
        else:
            if enabled is not None:
                _ORCH.set_enabled(bool(enabled))
        return _ORCH


def reset_orchestrator_for_tests() -> None:
    global _ORCH
    with _ORCH_LOCK:
        _ORCH = None
