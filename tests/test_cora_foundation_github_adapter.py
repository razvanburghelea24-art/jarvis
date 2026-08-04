"""TDD — GitHub Adapter (DispatchRequest → AdapterResult · mock transport)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.adapters import AdapterStatus, GitHubAdapter, MockGitHubTransport
from src.jarvis.cora_foundation.conversation import (
    ContextBuilder,
    DecisionEngine,
    RequestValidator,
    reset_conversation_event_journal_for_tests,
    reset_conversation_memory_for_tests,
)
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchOutcome,
    DispatchRequest,
    Dispatcher,
)
from src.jarvis.cora_foundation.planner import PlannerRouter
from src.jarvis.cora_foundation.tool_routing import ToolRouter


def setup_function():
    reset_conversation_event_journal_for_tests()
    reset_conversation_memory_for_tests()


def _req(
    tool: str,
    *,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
) -> DispatchRequest:
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_gh",
        tool=tool,
        capability="github.write" if "read" not in tool and "list" not in tool else "github.read",
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload or {"repo": "owner/repo"},
        metadata={"test": True},
    )


def test_create_pr():
    r = GitHubAdapter().execute(
        _req(
            "GitHub.create_pr",
            payload={"repo": "nymods/overlay", "title": "feat: test", "head": "feat", "base": "main"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.adapter == "github"
    assert r.operation == "create_pr"
    assert r.external_id
    assert r.error is None
    assert r.metadata.get("live") is False


def test_create_issue():
    r = GitHubAdapter().execute(
        _req("GitHub.create_issue", payload={"repo": "nymods/overlay", "title": "bug"})
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "create_issue"


def test_comment_pr():
    r = GitHubAdapter().execute(
        _req(
            "GitHub.comment_pr",
            payload={"repo": "nymods/overlay", "pr_number": 12, "body": "LGTM"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "comment_pr"


def test_read_repo():
    r = GitHubAdapter().execute(
        _req(
            "GitHub.read_repo",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"repo": "nymods/overlay"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "read_repo"
    assert r.external_id == "nymods/overlay"


def test_approval_missing_deny():
    r = GitHubAdapter().execute(
        _req(
            "GitHub.create_pr",
            approval=ApprovalState.PENDING,
            payload={"repo": "o/r", "title": "x"},
        )
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "DENY"


def test_invalid_dispatch_request():
    r = GitHubAdapter().execute(None)  # type: ignore[arg-type]
    assert r.status == AdapterStatus.FAILED
    assert r.error == "INVALID_DISPATCH_REQUEST"

    r2 = GitHubAdapter().execute({"tool": "GitHub.create_pr"})  # type: ignore[arg-type]
    assert r2.error == "INVALID_DISPATCH_REQUEST"

    r3 = GitHubAdapter().execute(
        _req("Discord.send", payload={"repo": "o/r", "title": "x"})
    )
    assert r3.error == "INVALID_DISPATCH_REQUEST"


def test_unsupported_operation():
    r = GitHubAdapter().execute(
        _req("GitHub.delete_repo", payload={"repo": "o/r"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "UNSUPPORTED_OPERATION"


def test_missing_repo_no_invention():
    r = GitHubAdapter().execute(
        _req("GitHub.create_pr", payload={"title": "no repo"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "MISSING_REPO"


def test_json_immutable():
    r = GitHubAdapter().execute(
        _req("GitHub.list_branches", approval=ApprovalState.NOT_REQUIRED)
    )
    raw = r.to_canonical_dict()
    assert raw["schema_family"] == "cora.adapter.contracts"
    assert raw["kind"] == "AdapterResult"
    assert json.dumps(raw)
    with pytest.raises(Exception):
        r.status = AdapterStatus.FAILED  # type: ignore[misc]


def test_harness_dispatcher_to_github_adapter():
    """Only path: Planner→ToolPlan→Dispatcher→approved DispatchRequest→GitHubAdapter."""
    req = RequestValidator().validate(
        {
            "request_id": "req-gh-harness",
            "session_id": "sess-gh",
            "workspace_id": "ws",
            "input": "Creează un PR pe GitHub",
        }
    )
    ctx = ContextBuilder().build(req)
    dec = DecisionEngine().decide(req, ctx)
    planner = PlannerRouter().route(req, ctx, dec)
    plan = ToolRouter().route(planner, req)
    batch = Dispatcher().dispatch(plan, approval_granted=True)
    assert batch.outcome == DispatchOutcome.READY
    assert batch.requests

    gh_req = batch.requests[0]
    # Adapter does not invent repo — payload must carry it
    enriched = DispatchRequest(
        dispatch_id=gh_req.dispatch_id,
        plan_id=gh_req.plan_id,
        tool=gh_req.tool,
        capability=gh_req.capability,
        execution_mode=gh_req.execution_mode,
        approval_state=gh_req.approval_state,
        payload={
            "repo": "razvanburghelea24-art/jarvis",
            "title": "feat: harness pr",
            "head": "feature/test",
            "base": "main",
        },
        metadata=dict(gh_req.metadata),
        timestamp=gh_req.timestamp,
    )
    result = GitHubAdapter(MockGitHubTransport()).execute(enriched)
    assert result.status == AdapterStatus.SUCCESS
    assert result.operation == "create_pr"
    assert result.metadata.get("live") is False
