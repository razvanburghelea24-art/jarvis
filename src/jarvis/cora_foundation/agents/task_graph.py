"""Task Graph — DAG of specialist tasks (not a flat list)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable
import uuid

from .types import AgentRole


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    WAITING = "WAITING"  # waiting on approval / external gate
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


@dataclass
class TaskNode:
    task_id: str
    title: str
    agent_role: AgentRole
    depends_on: tuple[str, ...] = ()
    plan_id: str | None = None
    plan_step_id: str | None = None
    capability: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    result_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Orchestrator-owned scheduling fields (Planner still creates the node)
    retry_count: int = 0
    max_retry: int = 2
    backoff_s: float = 0.0
    failure_reason: str | None = None
    requires_owner_approval: bool = False
    owner_approved: bool = False
    blocked_reason: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "agent_role": self.agent_role.value,
            "depends_on": list(self.depends_on),
            "plan_id": self.plan_id,
            "plan_step_id": self.plan_step_id,
            "capability": self.capability,
            "status": self.status.value,
            "result_id": self.result_id,
            "metadata": dict(self.metadata),
            "retry_count": self.retry_count,
            "max_retry": self.max_retry,
            "backoff_s": self.backoff_s,
            "failure_reason": self.failure_reason,
            "requires_owner_approval": self.requires_owner_approval,
            "owner_approved": self.owner_approved,
            "blocked_reason": self.blocked_reason,
        }


class TaskGraph:
    """Directed acyclic task graph. Parallelism = multiple READY nodes."""

    def __init__(self, *, graph_id: str | None = None, plan_id: str | None = None) -> None:
        self.graph_id = graph_id or f"tg_{uuid.uuid4().hex[:12]}"
        self.plan_id = plan_id
        self._nodes: dict[str, TaskNode] = {}

    def add(self, node: TaskNode) -> None:
        if node.task_id in self._nodes:
            raise ValueError(f"duplicate task_id: {node.task_id}")
        for dep in node.depends_on:
            if dep not in self._nodes and dep not in {n.task_id for n in self._nodes.values()}:
                # allow forward refs only if dep will be added; validate later
                pass
        self._nodes[node.task_id] = node

    def get(self, task_id: str) -> TaskNode | None:
        return self._nodes.get(task_id)

    def nodes(self) -> list[TaskNode]:
        return list(self._nodes.values())

    def validate(self) -> None:
        ids = set(self._nodes)
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in ids:
                    raise ValueError(f"{node.task_id} depends on missing {dep}")
        # cycle check
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(tid: str) -> None:
            if tid in visited:
                return
            if tid in visiting:
                raise ValueError(f"cycle detected at {tid}")
            visiting.add(tid)
            for dep in self._nodes[tid].depends_on:
                dfs(dep)
            visiting.remove(tid)
            visited.add(tid)

        for tid in self._nodes:
            dfs(tid)

    def _deps_satisfied(self, node: TaskNode) -> bool:
        return all(self._nodes[d].status == TaskStatus.COMPLETED for d in node.depends_on)

    def ready_tasks(self) -> list[TaskNode]:
        """Tasks whose dependencies are COMPLETED — eligible for parallel run."""
        ready: list[TaskNode] = []
        for node in self._nodes.values():
            if node.status not in {TaskStatus.PENDING, TaskStatus.READY}:
                continue
            if self._deps_satisfied(node):
                node.status = TaskStatus.READY
                ready.append(node)
        return ready

    def ready_task_ids(self) -> list[str]:
        return [
            n.task_id
            for n in self._nodes.values()
            if n.status in {TaskStatus.PENDING, TaskStatus.READY} and self._deps_satisfied(n)
        ]

    def mark_running(self, task_id: str) -> None:
        node = self._nodes[task_id]
        node.status = TaskStatus.RUNNING

    def mark_completed(self, task_id: str, *, result_id: str) -> None:
        node = self._nodes[task_id]
        node.status = TaskStatus.COMPLETED
        node.result_id = result_id

    def mark_failed(self, task_id: str, *, result_id: str | None = None) -> None:
        node = self._nodes[task_id]
        node.status = TaskStatus.FAILED
        if result_id:
            node.result_id = result_id

    def is_complete(self) -> bool:
        return all(
            n.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED}
            for n in self._nodes.values()
        )

    def parallel_ready_count(self) -> int:
        return len(self.ready_task_ids())

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "nodes": [n.to_public_dict() for n in self._nodes.values()],
            "ready": self.ready_task_ids(),
        }


def graph_from_plan(plan: Any) -> TaskGraph:
    """
    Build a specialist Task Graph from a Planner Plan.

    Mapping heuristic (Planner remains boss — this is structural only):
    Research → early observe steps
    Code → implementation / capability proposal steps
    Review → review-like
    Validation → final await / validation-like
    """
    from ..planner.types import Plan, PlanKind

    if not isinstance(plan, Plan):
        raise TypeError("graph_from_plan expects Plan")

    g = TaskGraph(plan_id=plan.plan_id)
    kind = plan.kind

    # Default pipeline graph — can fan out for parallel research/review later.
    research = TaskNode(
        task_id=new_task_id(),
        title="Research / observe context",
        agent_role=AgentRole.RESEARCH,
        plan_id=plan.plan_id,
        depends_on=(),
    )
    g.add(research)

    if kind in {PlanKind.IMPLEMENTATION, PlanKind.MIGRATION, PlanKind.CLEANUP, PlanKind.RELEASE, PlanKind.ROLLBACK}:
        code = TaskNode(
            task_id=new_task_id(),
            title="Code / implement proposed changes",
            agent_role=AgentRole.CODE,
            plan_id=plan.plan_id,
            depends_on=(research.task_id,),
            capability=plan.required_capabilities[0] if plan.required_capabilities else None,
        )
        g.add(code)
        review_deps: tuple[str, ...] = (code.task_id,)
    else:
        review_deps = (research.task_id,)

    review = TaskNode(
        task_id=new_task_id(),
        title="Review findings / architecture / regressions",
        agent_role=AgentRole.REVIEW,
        plan_id=plan.plan_id,
        depends_on=review_deps,
    )
    g.add(review)

    validation = TaskNode(
        task_id=new_task_id(),
        title="Validate tests / compliance",
        agent_role=AgentRole.VALIDATION,
        plan_id=plan.plan_id,
        depends_on=(review.task_id,),
    )
    g.add(validation)
    g.validate()
    return g


def merge_parallel_roots(nodes: Iterable[TaskNode], *, plan_id: str | None = None) -> TaskGraph:
    """Helper: multiple independent roots → parallel READY set."""
    g = TaskGraph(plan_id=plan_id)
    for n in nodes:
        g.add(n)
    g.validate()
    return g
