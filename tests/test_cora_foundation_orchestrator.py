"""Phase 5.5 — Agent Orchestrator / Scheduler."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.agents import (
    AgentResult,
    AgentResultStatus,
    AgentRole,
    AgentRuntime,
    QualityScores,
    TaskGraph,
    TaskNode,
    TaskStatus,
    graph_from_plan,
)
from src.jarvis.cora_foundation.audit import (
    AuditEngine,
    AuditEventType,
    reset_audit_engine_for_tests,
)
from src.jarvis.cora_foundation.orchestrator import (
    ENV_ENABLED,
    AgentOrchestrator,
    OrchestratorConfig,
    ResourceHint,
    get_orchestrator,
    orchestrator_enabled_from_env,
    render_progress_bars,
    reset_orchestrator_for_tests,
)
from src.jarvis.cora_foundation.planner import PlannerContext, PlannerEngine


ORCH_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "orchestrator"


@pytest.fixture(autouse=True)
def _reset():
    reset_orchestrator_for_tests()
    reset_audit_engine_for_tests()
    yield
    reset_orchestrator_for_tests()
    reset_audit_engine_for_tests()


def _result(task_id: str, role: AgentRole, *, confidence: float, status=AgentResultStatus.COMPLETED) -> AgentResult:
    return AgentResult(
        result_id=f"ares_{task_id}",
        agent_role=role,
        task_id=task_id,
        plan_id="p1",
        status=status,
        summary="done",
        confidence=confidence,
        quality=QualityScores(),
    )


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert orchestrator_enabled_from_env() is False
    orch = get_orchestrator()
    assert orch.enabled is False
    g = TaskGraph()
    g.add(TaskNode(task_id="a", title="A", agent_role=AgentRole.RESEARCH))
    orch.bind_graph(g)
    assert orch.graph() is None
    assert orch.select_wave() == []


def test_never_invents_tasks():
    orch = AgentOrchestrator(enabled=True)
    with pytest.raises(RuntimeError, match="must not invent"):
        orch.invent_task(title="x")
    with pytest.raises(RuntimeError, match="must not invent"):
        orch.add_task(title="x")


def test_parallel_wave_selection():
    orch = AgentOrchestrator(enabled=True)
    g = TaskGraph(plan_id="p")
    a = TaskNode(task_id="a", title="Research", agent_role=AgentRole.RESEARCH)
    b = TaskNode(task_id="b", title="Code", agent_role=AgentRole.CODE, depends_on=("a",))
    c = TaskNode(task_id="c", title="Docs", agent_role=AgentRole.REVIEW, depends_on=("a",))
    d = TaskNode(task_id="d", title="Validation", agent_role=AgentRole.VALIDATION, depends_on=("b", "c"))
    for n in (a, b, c, d):
        g.add(n)
    # CODE normally needs approval — disable for parallelism unit test
    b.requires_owner_approval = False
    orch = AgentOrchestrator(
        enabled=True,
        config=OrchestratorConfig(approval_roles=(), confidence_thresholds={"Code": 0.0, "Validation": 0.0}),
    )
    orch.bind_graph(g)
    wave1 = {n.task_id for n in orch.select_wave()}
    assert wave1 == {"a"}
    orch.mark_started("a")
    orch.report_result("a", _result("a", AgentRole.RESEARCH, confidence=0.95))
    wave2 = {n.task_id for n in orch.select_wave()}
    assert wave2 == {"b", "c"}  # true parallel


def test_confidence_gate_blocks_code_allows_review(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    orch = AgentOrchestrator(
        enabled=True,
        audit=audit,
        config=OrchestratorConfig(
            confidence_thresholds={"Code": 0.50, "Validation": 0.0},
            approval_roles=(),
        ),
    )
    g = TaskGraph(plan_id="p")
    r = TaskNode(task_id="r", title="Research", agent_role=AgentRole.RESEARCH)
    code = TaskNode(task_id="code", title="Code", agent_role=AgentRole.CODE, depends_on=("r",))
    rev = TaskNode(task_id="rev", title="Review", agent_role=AgentRole.REVIEW, depends_on=("r", "code"))
    for n in (r, code, rev):
        g.add(n)
    orch.bind_graph(g)
    orch.mark_started("r")
    orch.report_result("r", _result("r", AgentRole.RESEARCH, confidence=0.42))
    code_node = g.get("code")
    assert code_node is not None
    assert code_node.status == TaskStatus.BLOCKED
    assert code_node.blocked_reason == "confidence_gate"
    # Review can become READY despite code blocked by confidence
    orch.sync_states()
    rev_node = g.get("rev")
    assert rev_node is not None
    assert rev_node.status == TaskStatus.READY
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.TASK_BLOCKED in types


def test_retry_policy(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    orch = AgentOrchestrator(
        enabled=True,
        audit=audit,
        config=OrchestratorConfig(approval_roles=(), confidence_thresholds={}),
    )
    g = TaskGraph()
    t = TaskNode(task_id="t1", title="Research", agent_role=AgentRole.RESEARCH, max_retry=2)
    g.add(t)
    orch.bind_graph(g)
    orch.mark_started("t1")
    orch.report_result(
        "t1",
        _result("t1", AgentRole.RESEARCH, confidence=0.5, status=AgentResultStatus.FAILED),
    )
    assert t.retry_count == 1
    assert t.status == TaskStatus.READY  # re-queued
    assert t.backoff_s > 0
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.TASK_RETRIED in types


def test_owner_approval_gate():
    orch = AgentOrchestrator(
        enabled=True,
        config=OrchestratorConfig(
            approval_roles=("Code",),
            confidence_thresholds={"Code": 0.0},
        ),
    )
    g = TaskGraph()
    r = TaskNode(task_id="r", title="Research", agent_role=AgentRole.RESEARCH)
    c = TaskNode(task_id="c", title="Code", agent_role=AgentRole.CODE, depends_on=("r",), capability="GitHub.create_pr")
    g.add(r)
    g.add(c)
    orch.bind_graph(g)
    orch.mark_started("r")
    orch.report_result("r", _result("r", AgentRole.RESEARCH, confidence=0.9))
    assert c.status == TaskStatus.WAITING
    with pytest.raises(PermissionError):
        orch.approve("c", owner_id="")
    orch.approve("c", owner_id="own_boss")
    assert c.status == TaskStatus.READY


def test_resource_hints_opaque_to_agents():
    orch = AgentOrchestrator(enabled=True)
    node = TaskNode(task_id="r", title="R", agent_role=AgentRole.RESEARCH)
    assert orch.resource_hint(node) == ResourceHint.DEEP_MODEL
    code = TaskNode(task_id="c", title="C", agent_role=AgentRole.CODE)
    assert orch.resource_hint(code) == ResourceHint.FAST_MODEL


def test_observability_bars():
    orch = AgentOrchestrator(enabled=True, config=OrchestratorConfig(approval_roles=()))
    g = TaskGraph()
    g.add(TaskNode(task_id="r", title="Research", agent_role=AgentRole.RESEARCH))
    orch.bind_graph(g)
    prog = orch.progress()
    assert prog is not None
    rendered = render_progress_bars(prog)
    assert "Research" in rendered
    assert "█" in rendered or "░" in rendered
    assert "bars" in prog.to_public_dict()


def test_run_specialist_wave_delegates_not_dispatch(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    runtime = AgentRuntime(enabled=True, audit=audit)
    orch = AgentOrchestrator(
        enabled=True,
        audit=audit,
        runtime=runtime,
        config=OrchestratorConfig(approval_roles=(), confidence_thresholds={"Validation": 0.0, "Code": 0.0}),
    )
    planner = PlannerEngine(enabled=True)
    plan = planner.create_plan(
        PlannerContext(
            request_id="req",
            request_text="analyze health",
            identity={"who": "own"},
            memory_snapshot={"record_count": 4},
            integration_snapshots=({"source": "github"},),
        )
    )
    assert plan is not None
    g = graph_from_plan(plan)
    orch.bind_graph(g)
    # Drive until complete or stalled (approval/confidence)
    guard = 0
    while not g.is_complete() and guard < 12:
        wave = orch.select_wave()
        if not wave:
            break
        orch.run_specialist_wave(
            context={"identity": {"who": "own"}, "integration_count": 1, "memory_snapshot": {"record_count": 4}}
        )
        guard += 1
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.TASK_READY in types
    assert AuditEventType.TASK_STARTED in types
    assert AuditEventType.TASK_COMPLETED in types
    st = orch.status()
    assert st["invents_tasks"] is False
    assert st["dispatches_live"] is False


def test_no_dispatcher_imports():
    for path in ORCH_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                assert "dispatcher" not in mod
                if node.level == 0 and mod and not mod.startswith("src") and "cora_foundation" not in mod:
                    root = mod.split(".")[0]
                    assert root not in {"requests", "httpx", "openai", "anthropic"}
