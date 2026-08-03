"""Live-ish progress snapshot for Visual Brain later."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..agents.task_graph import TaskGraph, TaskStatus


_BAR_WIDTH = 10

_STATUS_FILL = {
    TaskStatus.COMPLETED: 10,
    TaskStatus.RUNNING: 6,
    TaskStatus.READY: 3,
    TaskStatus.WAITING: 2,
    TaskStatus.BLOCKED: 1,
    TaskStatus.FAILED: 1,
    TaskStatus.PENDING: 0,
    TaskStatus.SKIPPED: 0,
}


@dataclass(frozen=True)
class GraphProgress:
    graph_id: str
    plan_id: str | None
    bars: tuple[dict[str, Any], ...]
    completed: int
    total: int
    parallel_ready: int
    needs_owner_approval: tuple[str, ...]
    blocked: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "bars": list(self.bars),
            "completed": self.completed,
            "total": self.total,
            "parallel_ready": self.parallel_ready,
            "needs_owner_approval": list(self.needs_owner_approval),
            "blocked": list(self.blocked),
            "rendered": render_progress_bars(self),
        }


def _bar(filled: int) -> str:
    filled = max(0, min(_BAR_WIDTH, filled))
    return ("█" * filled) + ("░" * (_BAR_WIDTH - filled))


def render_progress_bars(progress: GraphProgress | TaskGraph) -> str:
    if isinstance(progress, TaskGraph):
        progress = snapshot_progress(progress)
    lines = []
    for row in progress.bars:
        label = str(row["label"]).ljust(14)
        lines.append(f"{label}{row['bar']}")
    return "\n".join(lines)


def snapshot_progress(graph: TaskGraph) -> GraphProgress:
    bars: list[dict[str, Any]] = []
    completed = 0
    waiting: list[str] = []
    blocked: list[str] = []
    for node in graph.nodes():
        fill = _STATUS_FILL.get(node.status, 0)
        if node.status == TaskStatus.COMPLETED:
            completed += 1
        if node.status == TaskStatus.WAITING or (
            node.requires_owner_approval and not node.owner_approved and node.status != TaskStatus.COMPLETED
        ):
            waiting.append(node.task_id)
        if node.status == TaskStatus.BLOCKED:
            blocked.append(node.task_id)
        bars.append(
            {
                "task_id": node.task_id,
                "label": node.agent_role.value,
                "title": node.title,
                "status": node.status.value,
                "fill": fill,
                "bar": _bar(fill),
            }
        )
    return GraphProgress(
        graph_id=graph.graph_id,
        plan_id=graph.plan_id,
        bars=tuple(bars),
        completed=completed,
        total=len(graph.nodes()),
        parallel_ready=graph.parallel_ready_count(),
        needs_owner_approval=tuple(waiting),
        blocked=tuple(blocked),
    )
