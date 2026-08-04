"""TDD — GitHub LIVE (phased · Gateway-gated · stub HTTP · no network required)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.jarvis.cora_foundation.adapters import AdapterStatus, GitHubAdapter
from src.jarvis.cora_foundation.adapters.github.live_transport import LiveGitHubTransport
from src.jarvis.cora_foundation.adapters.github.path import execute_github_gated
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchRequest,
)
from src.jarvis.cora_foundation.live_gateway import (
    ExecutionMode,
    GatewayContext,
    GatewayVerdict,
)


def _req(
    tool: str,
    *,
    capability: str | None = None,
    approval: ApprovalState = ApprovalState.GRANTED,
    payload: dict | None = None,
) -> DispatchRequest:
    write = any(
        x in tool
        for x in ("create", "comment")
    )
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="tplan_gh_live",
        tool=tool,
        capability=capability
        or ("github.write" if write else "github.read"),
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=approval,
        payload=payload
        if payload is not None
        else {"repo": "owner/repo", "title": "t", "head": "feat", "base": "main"},
        metadata={"test": True},
    )


def _ctx(**kwargs) -> GatewayContext:
    base = dict(
        session_id="sess_live",
        workspace_id="ws_live",
        session_valid=True,
        workspace_active=True,
        e_stop=False,
        safe_mode=False,
        rate_limit_ok=True,
        audit_available=True,
        mode=ExecutionMode.LIVE,
    )
    base.update(kwargs)
    return GatewayContext(**base)


def _stub_http(responses: dict[str, tuple[int, Any]]):
    def http(method: str, url: str, headers, body):
        # match by method + path suffix key
        for key, val in responses.items():
            m, path = key.split(" ", 1)
            if method == m and path in url:
                return val
        return 404, {"message": f"unmocked {method} {url}"}

    return http


def _live(phase: int, http) -> LiveGitHubTransport:
    return LiveGitHubTransport(token="test-token", phase=phase, http=http)


def test_read_repo_live():
    http = _stub_http({"GET /repos/owner/repo": (200, {"full_name": "owner/repo", "default_branch": "main"})})
    t = _live(1, http)
    r = GitHubAdapter(t).execute(
        _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "owner/repo"})
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "read_repo"
    assert r.metadata.get("live") is True


def test_read_pr_live():
    http = _stub_http({"GET /repos/owner/repo/pulls/3": (200, {"number": 3, "state": "open"})})
    r = GitHubAdapter(_live(1, http)).execute(
        _req(
            "GitHub.read_pr",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"repo": "owner/repo", "pr_number": 3},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "read_pr"


def test_list_branches_live():
    http = _stub_http(
        {"GET /repos/owner/repo/branches": (200, [{"name": "main"}, {"name": "dev"}])}
    )
    r = GitHubAdapter(_live(1, http)).execute(
        _req(
            "GitHub.list_branches",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"repo": "owner/repo"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert "main" in (r.metadata.get("data") or {}).get("branches", [])


def test_phase1_locks_writes():
    http = _stub_http({})
    r = GitHubAdapter(_live(1, http)).execute(
        _req("GitHub.create_issue", payload={"repo": "owner/repo", "title": "x"})
    )
    assert r.status == AdapterStatus.FAILED
    assert r.error == "PHASE_LOCKED"


def test_create_issue_phase2():
    http = _stub_http(
        {"POST /repos/owner/repo/issues": (201, {"number": 9, "title": "x"})}
    )
    r = GitHubAdapter(_live(2, http)).execute(
        _req("GitHub.create_issue", payload={"repo": "owner/repo", "title": "x"})
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "create_issue"


def test_comment_issue_phase2():
    http = _stub_http(
        {"POST /repos/owner/repo/issues/9/comments": (201, {"id": 55, "body": "hi"})}
    )
    r = GitHubAdapter(_live(2, http)).execute(
        _req(
            "GitHub.comment_issue",
            payload={"repo": "owner/repo", "issue_number": 9, "body": "hi"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS


def test_comment_pr_phase2():
    http = _stub_http(
        {"POST /repos/owner/repo/issues/3/comments": (201, {"id": 56, "body": "lgtm"})}
    )
    r = GitHubAdapter(_live(2, http)).execute(
        _req(
            "GitHub.comment_pr",
            payload={"repo": "owner/repo", "pr_number": 3, "body": "lgtm"},
        )
    )
    assert r.status == AdapterStatus.SUCCESS


def test_create_pr_phase3():
    http = _stub_http(
        {"POST /repos/owner/repo/pulls": (201, {"number": 12, "html_url": "https://x"})}
    )
    r = GitHubAdapter(_live(3, http)).execute(
        _req(
            "GitHub.create_pr",
            payload={
                "repo": "owner/repo",
                "title": "feat",
                "head": "feat",
                "base": "main",
            },
        )
    )
    assert r.status == AdapterStatus.SUCCESS
    assert r.operation == "create_pr"
    assert r.external_id == "owner/repo#12"


def test_phase2_locks_create_pr():
    r = GitHubAdapter(_live(2, _stub_http({}))).execute(_req("GitHub.create_pr"))
    assert r.error == "PHASE_LOCKED"


def test_gated_approval_missing_deny_no_adapter():
    called = {"n": 0}

    def http(*_a, **_k):
        called["n"] += 1
        return 200, {}

    out = execute_github_gated(
        _req("GitHub.read_repo", approval=ApprovalState.PENDING, payload={"repo": "o/r"}),
        _ctx(),
        transport=_live(1, http),
    )
    assert out.gateway.decision == GatewayVerdict.DENY
    assert out.adapter is None
    assert called["n"] == 0


def test_gated_e_stop_deny():
    out = execute_github_gated(
        _req("GitHub.read_repo", approval=ApprovalState.NOT_REQUIRED, payload={"repo": "o/r"}),
        _ctx(e_stop=True),
        transport=_live(1, _stub_http({})),
    )
    assert out.gateway.reason == "E_STOP"
    assert out.adapter is None


def test_gated_safe_mode_write_deny():
    out = execute_github_gated(
        _req("GitHub.create_issue", payload={"repo": "o/r", "title": "x"}),
        _ctx(safe_mode=True),
        transport=_live(2, _stub_http({})),
    )
    assert out.gateway.reason == "SAFE_MODE_WRITE_BLOCKED"
    assert out.adapter is None


def test_gated_live_allow_with_audit_path():
    audits: list = []

    def on_audit(d):
        audits.append(d.to_canonical_dict())
        return True

    from src.jarvis.cora_foundation.live_gateway import LiveExecutionGateway

    http = _stub_http(
        {"GET /repos/owner/repo": (200, {"full_name": "owner/repo"})}
    )
    out = execute_github_gated(
        _req(
            "GitHub.read_repo",
            approval=ApprovalState.NOT_REQUIRED,
            payload={"repo": "owner/repo"},
        ),
        _ctx(mode=ExecutionMode.LIVE),
        gateway=LiveExecutionGateway(on_audit=on_audit),
        transport=_live(1, http),
    )
    assert out.allowed is True
    assert out.adapter is not None
    assert out.adapter.status == AdapterStatus.SUCCESS
    assert audits  # audit trail created
    assert json.dumps(out.gateway.to_canonical_dict())
