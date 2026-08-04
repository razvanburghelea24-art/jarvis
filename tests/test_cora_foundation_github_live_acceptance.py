"""GitHub LIVE Acceptance Suite — PRODUCTION READY gate."""

from __future__ import annotations

import json

from src.jarvis.cora_foundation.adapters.github.acceptance import run_acceptance_suite
from src.jarvis.cora_foundation.adapters.github.metrics import ChainMetrics
from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    DecisionEngine,
    RequestValidator,
    reset_conversation_event_journal_for_tests,
    reset_conversation_memory_for_tests,
)
from src.jarvis.cora_foundation.dispatcher import Dispatcher
from src.jarvis.cora_foundation.adapters.github.metrics import Timer
from src.jarvis.cora_foundation.live_gateway import ExecutionMode, GatewayContext
from src.jarvis.cora_foundation.adapters.github.acceptance import _ctx, _req, _transport
from src.jarvis.cora_foundation.adapters.github.path import execute_github_gated
from src.jarvis.cora_foundation.planner import PlannerRouter
from src.jarvis.cora_foundation.tool_routing import ToolRouter
from src.jarvis.cora_foundation.dispatcher import ApprovalState, DispatchRequest


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def test_acceptance_suite_production_ready():
    report = run_acceptance_suite()
    assert report.passed, json.dumps(report.to_dict(), indent=2)
    assert report.to_dict()["verdict"] == "PRODUCTION_READY"
    names = {s.name for s in report.scenarios}
    required = {
        "read_repo",
        "read_pr",
        "list_branches",
        "create_issue",
        "comment_issue",
        "comment_pr",
        "create_pr",
        "audit_complete",
        "gateway_approval_missing",
        "rollback_e_stop",
        "e_stop_during_execution",
        "safe_mode",
        "rate_limit",
        "phase_locked",
        "token_invalid",
        "repo_invalid",
    }
    assert required <= names


def test_end_to_end_chain_metrics_create_pr():
    """Planner→ToolPlan→Dispatcher→Gateway→GitHub with timing panel."""
    metrics = ChainMetrics()

    t = Timer()
    req = RequestValidator().validate(
        {
            "request_id": "req-accept-e2e",
            "session_id": "sess-accept-e2e",
            "workspace_id": "ws",
            "input": "Creează un PR pe GitHub",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    metrics.conversation_ms = t.ms()

    t = Timer()
    planner = PlannerRouter().route(req, ctx, dec)
    metrics.planner_ms = t.ms()

    t = Timer()
    plan = ToolRouter().route(planner, req)
    metrics.tool_routing_ms = t.ms()

    t = Timer()
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    metrics.dispatcher_ms = t.ms()
    assert batch.requests
    base = batch.requests[0]

    enriched = DispatchRequest(
        dispatch_id=base.dispatch_id,
        plan_id=base.plan_id,
        tool=base.tool,
        capability=base.capability,
        execution_mode=base.execution_mode,
        approval_state=base.approval_state,
        payload={
            "repo": "owner/demo",
            "title": "feat: acceptance",
            "head": "feat",
            "base": "main",
        },
        metadata=dict(base.metadata),
        timestamp=base.timestamp,
    )

    from src.jarvis.cora_foundation.adapters.github.acceptance import _default_stub_http

    transport = _transport(3, _default_stub_http())
    t = Timer()
    out = execute_github_gated(
        enriched,
        GatewayContext(
            session_id=req.session_id,
            workspace_id=req.workspace_id,
            session_valid=True,
            workspace_active=True,
            mode=ExecutionMode.LIVE,
        ),
        transport=transport,
    )
    metrics.gateway_ms = t.ms()
    metrics.github_ms = float((out.adapter.duration * 1000.0) if out.adapter else 0.0)

    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.operation == "create_pr"
    panel = "\n".join(metrics.panel_lines())
    assert "TOTAL:" in panel
    assert metrics.total_ms >= 0
    raw = metrics.to_dict()
    assert "gateway_ms" in raw
