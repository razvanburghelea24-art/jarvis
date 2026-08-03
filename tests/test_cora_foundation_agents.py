"""Phase 5 — Specialist Agents (result-only) + Task Graph."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.agents import (
    ENV_ENABLED,
    AgentResult,
    AgentResultStatus,
    AgentRole,
    AgentRuntime,
    QualityScores,
    TaskGraph,
    TaskNode,
    TaskStatus,
    agents_enabled_from_env,
    get_agent_runtime,
    graph_from_plan,
    reset_agent_runtime_for_tests,
)
from src.jarvis.cora_foundation.agents.code import CodeAgent
from src.jarvis.cora_foundation.agents.research import ResearchAgent
from src.jarvis.cora_foundation.agents.review import ReviewAgent
from src.jarvis.cora_foundation.agents.validation import ValidationAgent
from src.jarvis.cora_foundation.audit import (
    AuditEngine,
    AuditEventType,
    reset_audit_engine_for_tests,
)
from src.jarvis.cora_foundation.planner import PlannerContext, PlannerEngine


AGENTS_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "agents"

_FORBIDDEN_METHODS = (
    "dispatch",
    "execute_capability",
    "approve_owner",
    "write_memory",
    "deploy",
    "send_discord",
)


@pytest.fixture(autouse=True)
def _reset():
    reset_agent_runtime_for_tests()
    reset_audit_engine_for_tests()
    yield
    reset_agent_runtime_for_tests()
    reset_audit_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert agents_enabled_from_env() is False
    rt = get_agent_runtime()
    assert rt.enabled is False
    task = TaskNode(task_id="t1", title="x", agent_role=AgentRole.RESEARCH)
    assert rt.run_task(task) is None


def test_agent_result_invariants():
    agent = ResearchAgent()
    task = TaskNode(task_id="t1", title="research", agent_role=AgentRole.RESEARCH, plan_id="p1")
    result = agent.run(task, context={"identity": {"who": "own"}, "integration_count": 2})
    assert isinstance(result, AgentResult)
    assert result.dispatches is False
    assert result.decides_architecture is False
    assert result.final_decision is False
    assert 0.0 <= result.confidence <= 1.0
    q = result.quality.to_public_dict()
    for key in ("architecture", "security", "performance", "complexity", "maintainability"):
        assert key in q
        assert 0.0 <= q[key] <= 1.0


def test_specialists_single_purpose_summaries():
    task = TaskNode(task_id="t", title="work", agent_role=AgentRole.CODE, capability="GitHub.create_pr")
    code = CodeAgent().run(task)
    assert "not applied" in code.summary.lower() or "proposal" in code.summary.lower()
    assert code.recommends_review is True
    assert code.proposed_capabilities == ("GitHub.create_pr",)

    review = ReviewAgent().run(
        TaskNode(task_id="r", title="review", agent_role=AgentRole.REVIEW),
        context={"prior_results": [{"confidence": 0.41}]},
    )
    assert review.artifacts.get("approves") is False
    assert any("0.50" in f for f in review.findings)

    val = ValidationAgent().run(
        TaskNode(task_id="v", title="val", agent_role=AgentRole.VALIDATION),
        context={"prior_results": [{"recommends_review": True}]},
    )
    assert val.artifacts.get("dispatched") is False
    assert val.artifacts.get("owner_approval_required") is True


def test_task_graph_is_dag_not_list():
    g = TaskGraph(plan_id="p")
    a = TaskNode(task_id="a", title="A", agent_role=AgentRole.RESEARCH)
    b = TaskNode(task_id="b", title="B", agent_role=AgentRole.CODE, depends_on=("a",))
    c = TaskNode(task_id="c", title="C", agent_role=AgentRole.REVIEW, depends_on=("a",))
    d = TaskNode(task_id="d", title="D", agent_role=AgentRole.VALIDATION, depends_on=("b", "c"))
    for n in (a, b, c, d):
        g.add(n)
    g.validate()
    ready = g.ready_tasks()
    assert [n.task_id for n in ready] == ["a"]
    g.mark_completed("a", result_id="r1")
    ready2 = {n.task_id for n in g.ready_tasks()}
    assert ready2 == {"b", "c"}  # parallel fan-out


def test_task_graph_rejects_cycles():
    g = TaskGraph()
    g.add(TaskNode(task_id="a", title="A", agent_role=AgentRole.RESEARCH, depends_on=("b",)))
    g.add(TaskNode(task_id="b", title="B", agent_role=AgentRole.CODE, depends_on=("a",)))
    with pytest.raises(ValueError, match="cycle"):
        g.validate()


def test_graph_from_plan_pipeline():
    planner = PlannerEngine(enabled=True)
    plan = planner.create_plan(
        PlannerContext(request_id="req", request_text="implement overlay fix and create pr")
    )
    assert plan is not None
    g = graph_from_plan(plan)
    roles = [n.agent_role for n in g.nodes()]
    assert AgentRole.RESEARCH in roles
    assert AgentRole.CODE in roles
    assert AgentRole.REVIEW in roles
    assert AgentRole.VALIDATION in roles


def test_runtime_runs_wave_no_dispatch(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    rt = AgentRuntime(enabled=True, audit=audit)
    planner = PlannerEngine(enabled=True)
    plan = planner.create_plan(
        PlannerContext(
            request_id="req",
            request_text="analyze health",
            identity={"who": "own_boss"},
            memory_snapshot={"record_count": 3},
            integration_snapshots=({"source": "github"},),
        )
    )
    assert plan is not None
    g = graph_from_plan(plan)
    # Drive graph to completion wave by wave (Orchestrator lands in 5.5).
    guard = 0
    while not g.is_complete() and guard < 10:
        results = rt.run_ready(
            g,
            context={
                "identity": {"who": "own_boss"},
                "integration_count": 1,
                "memory_snapshot": {"record_count": 3},
            },
        )
        assert results
        for r in results:
            assert r.dispatches is False
            assert r.final_decision is False
        guard += 1
    assert g.is_complete()
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.AGENT_TASK_STARTED in types
    assert AuditEventType.AGENT_TASK_COMPLETED in types


def test_low_confidence_recommends_review():
    agent = ResearchAgent()
    # Sparse context → lower confidence → recommends_review
    result = agent.run(
        TaskNode(task_id="t", title="sparse", agent_role=AgentRole.RESEARCH),
        context={},
    )
    assert result.confidence < 0.50
    assert result.recommends_review is True


def test_quality_scores_clamped():
    q = QualityScores(architecture=1.5, security=-1.0, performance=0.5, complexity=0.2, maintainability=0.9)
    assert q.architecture == 1.0
    assert q.security == 0.0


def test_no_forbidden_methods_on_runtime():
    for name, _ in inspect.getmembers(AgentRuntime, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        lower = name.lower()
        for bad in _FORBIDDEN_METHODS:
            assert lower != bad
            assert not lower.startswith(bad + "_")


def test_no_dispatcher_or_network_imports():
    forbidden_roots = {"requests", "httpx", "openai", "anthropic", "discord", "socket"}
    joined = "\n".join(p.read_text(encoding="utf-8") for p in AGENTS_DIR.rglob("*.py"))
    assert "from ..gateway.dispatcher" not in joined
    assert "CommandGateway" not in joined
    assert "from ..memory" not in joined
    for path in AGENTS_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    # allow relative planner/audit only — block gateway dispatcher & memory
                    mod = (node.module or "").lower()
                    assert "dispatcher" not in mod
                    assert mod != "memory" and not mod.startswith("memory.")
                    continue
                mod = (node.module or "").lower()
                if "cora_foundation" in mod:
                    continue
                root = mod.split(".")[0]
                assert root not in forbidden_roots, f"{path.name} from {mod}"


def test_status_marks_orchestrator_future():
    rt = AgentRuntime(enabled=True)
    st = rt.status()
    assert st["orchestrator"] is False
    assert st["dispatches"] is False
    assert set(st["roles"]) == {"Research", "Code", "Review", "Validation"}
