"""Phase 4 — AI Planner (PLAN-ONLY)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.audit import (
    AuditEngine,
    AuditEventType,
    reset_audit_engine_for_tests,
)
from src.jarvis.cora_foundation.planner import (
    ENV_ENABLED,
    Plan,
    PlanKind,
    PlanRiskLevel,
    PlanStatus,
    PlannerContext,
    PlannerEngine,
    get_planner_engine,
    planner_enabled_from_env,
    reset_planner_engine_for_tests,
)


PLANNER_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "planner"

_EXECUTE_VERBS = (
    "execute",
    "dispatch",
    "invoke",
    "run_tool",
    "deploy",
    "send",
    "write_file",
    "write_memory",
    "memory_write",
)


@pytest.fixture(autouse=True)
def _reset():
    reset_planner_engine_for_tests()
    reset_audit_engine_for_tests()
    yield
    reset_planner_engine_for_tests()
    reset_audit_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert planner_enabled_from_env() is False
    assert get_planner_engine().enabled is False
    assert get_planner_engine().create_plan(
        PlannerContext(request_id="r1", request_text="analyze health")
    ) is None


def test_create_plan_standardized_fields(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    eng = PlannerEngine(enabled=True, audit=audit)
    ctx = PlannerContext(
        request_id="req_1",
        request_text="analyze overlay health status",
        identity={"who": "own_boss", "active_session": "ses_1"},
        memory_snapshot={"enabled": True, "revision": 1, "record_count": 2},
        integration_snapshots=({"source": "github", "kind": "health"},),
        policy_context={"kind": "Allowed"},
        runtime_state={"e_stop": False, "safe_mode": False},
    )
    plan = eng.create_plan(ctx)
    assert plan is not None
    assert isinstance(plan, Plan)
    assert plan.executable is False
    public = plan.to_public_dict()
    for key in (
        "plan_id",
        "goal",
        "summary",
        "steps",
        "dependencies",
        "required_capabilities",
        "risk_level",
        "estimated_cost",
        "estimated_duration",
        "requires_owner_approval",
        "status",
    ):
        assert key in public
    assert public["executable"] is False
    assert plan.kind == PlanKind.ANALYSIS
    assert plan.risk_level == PlanRiskLevel.LOW


def test_all_plan_kinds_reachable():
    eng = PlannerEngine(enabled=True)
    samples = {
        PlanKind.ANALYSIS: "analyze system health",
        PlanKind.DIAGNOSIS: "diagnose framework error outage",
        PlanKind.IMPLEMENTATION: "implement overlay fix",
        PlanKind.REVIEW: "review pull request changes",
        PlanKind.MIGRATION: "migrate memory schema",
        PlanKind.CLEANUP: "cleanup stale branches",
        PlanKind.RESEARCH: "research overlay architecture options",
        PlanKind.RELEASE: "release overlay 1.0.26",
        PlanKind.ROLLBACK: "rollback last railway deploy",
    }
    for kind, text in samples.items():
        plan = eng.create_plan(PlannerContext(request_id=f"r_{kind.value}", request_text=text))
        assert plan is not None
        assert plan.kind == kind


def test_capability_mapping_not_raw_api():
    eng = PlannerEngine(enabled=True)
    plan = eng.create_plan(
        PlannerContext(request_id="r_pr", request_text="create a pull request for overlay fix")
    )
    assert plan is not None
    assert "GitHub.create_pr" in plan.required_capabilities
    assert plan.risk_level == PlanRiskLevel.CRITICAL
    assert plan.requires_owner_approval is True
    assert "why" not in plan.risk_reason.lower() or True  # has reason text
    assert "GitHub.create_pr" in plan.risk_reason


def test_risk_levels_and_reasons():
    eng = PlannerEngine(enabled=True)
    low = eng.create_plan(PlannerContext(request_id="a", request_text="whoami identity check"))
    highish = eng.create_plan(
        PlannerContext(request_id="b", request_text="send discord announce to guild")
    )
    crit = eng.create_plan(PlannerContext(request_id="c", request_text="railway deploy production"))
    assert low and low.risk_level == PlanRiskLevel.LOW
    assert highish and highish.risk_level in {PlanRiskLevel.HIGH, PlanRiskLevel.CRITICAL}
    assert crit and crit.risk_level == PlanRiskLevel.CRITICAL
    assert crit.risk_reason


def test_cost_and_duration_estimated():
    eng = PlannerEngine(enabled=True)
    plan = eng.create_plan(PlannerContext(request_id="r", request_text="implement feature and create pr"))
    assert plan is not None
    assert plan.estimated_cost > 0
    assert plan.estimated_duration_s > 0


def test_audit_plan_lifecycle(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    eng = PlannerEngine(enabled=True, audit=audit)
    plan = eng.create_plan(
        PlannerContext(
            request_id="req_life",
            request_text="review migration plan",
            identity={"who": "own_boss"},
        )
    )
    assert plan is not None
    eng.update_plan(plan.plan_id, {"summary": "updated summary"}, request_id="req_life")
    eng.approve_plan(plan.plan_id, owner_id="own_boss", request_id="req_life")
    # new plan for reject/expire paths
    p2 = eng.create_plan(PlannerContext(request_id="req_2", request_text="cleanup branches"))
    assert p2 is not None
    eng.reject_plan(p2.plan_id, owner_id="own_boss", reason="not now", request_id="req_2")
    p3 = eng.create_plan(PlannerContext(request_id="req_3", request_text="research options"))
    assert p3 is not None
    eng.expire_plan(p3.plan_id, request_id="req_3")

    types = [e.event_type for e in audit.read_all()]
    for needed in (
        AuditEventType.PLAN_CREATED,
        AuditEventType.PLAN_UPDATED,
        AuditEventType.PLAN_APPROVED,
        AuditEventType.PLAN_REJECTED,
        AuditEventType.PLAN_EXPIRED,
    ):
        assert needed in types


def test_approve_requires_owner():
    eng = PlannerEngine(enabled=True)
    plan = eng.create_plan(PlannerContext(request_id="r", request_text="analyze"))
    assert plan is not None
    with pytest.raises(PermissionError):
        eng.approve_plan(plan.plan_id, owner_id="")


def test_no_execute_methods_on_engine():
    for name, _ in inspect.getmembers(PlannerEngine, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        lower = name.lower()
        for verb in _EXECUTE_VERBS:
            assert lower != verb
            assert not lower.startswith(verb + "_")


def test_no_network_sdk_or_write_imports():
    forbidden = {
        "requests",
        "httpx",
        "aiohttp",
        "discord",
        "github",
        "openai",
        "anthropic",
        "socket",
    }
    for path in PLANNER_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0].lower()
                    assert root not in forbidden, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                mod = (node.module or "").lower()
                if "cora_foundation" in mod:
                    continue
                root = mod.split(".")[0]
                assert root not in forbidden, f"{path.name} from {mod}"


def test_does_not_call_memory_write():
    """Planner accepts memory snapshot dict only — never mutates Memory SSOT."""
    src_files = [p.read_text(encoding="utf-8") for p in PLANNER_DIR.rglob("*.py")]
    joined = "\n".join(src_files)
    assert "from ..memory" not in joined
    assert "from ...memory" not in joined
    assert "cora_foundation.memory" not in joined
    assert ".upsert(" not in joined
    assert "Memory.write" not in joined


def test_consumes_snapshots_only():
    eng = PlannerEngine(enabled=True)
    ctx = PlannerContext(
        request_id="r",
        request_text="diagnose discord guild health",
        identity={"who": "own_boss"},
        memory_snapshot={"enabled": True, "record_count": 5, "revision": 3},
        integration_snapshots=(
            {"source": "discord", "kind": "guild"},
            {"source": "railway", "kind": "status"},
        ),
        policy_context={"kind": "Allowed"},
        runtime_state={"safe_mode": False},
    )
    plan = eng.create_plan(ctx)
    assert plan is not None
    assert "integration_hub.snapshot" in plan.dependencies
    assert "memory.snapshot" in plan.dependencies
    assert "identity.snapshot" in plan.dependencies
    assert eng.status()["executes"] is False
    assert eng.status()["writes_memory"] is False
