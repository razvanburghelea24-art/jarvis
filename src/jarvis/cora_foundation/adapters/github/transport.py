"""GitHub transport — injectable; default mock never hits the network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class GitHubTransportResult:
    ok: bool
    external_id: str | None = None
    data: Mapping[str, Any] | None = None
    error: str | None = None


class GitHubTransport(Protocol):
    def create_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def comment_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def create_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def comment_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def read_repo(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def read_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...

    def list_branches(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult: ...


class MockGitHubTransport:
    """Deterministic in-memory GitHub — live=False always."""

    live = False

    def create_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        title = str(payload.get("title") or "").strip()
        if not title:
            return GitHubTransportResult(ok=False, error="missing_title")
        n = int(payload.get("number") or (abs(hash(repo + title)) % 9000 + 1))
        return GitHubTransportResult(
            ok=True,
            external_id=f"{repo}#{n}",
            data={"number": n, "title": title, "html_url": f"https://github.com/{repo}/pull/{n}", "live": False},
        )

    def comment_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        pr = payload.get("pr_number") or payload.get("number")
        body = str(payload.get("body") or "").strip()
        if pr is None or not body:
            return GitHubTransportResult(ok=False, error="missing_pr_number_or_body")
        cid = f"prc_{uuid4().hex[:8]}"
        return GitHubTransportResult(
            ok=True,
            external_id=cid,
            data={"pr_number": int(pr), "body": body, "live": False},
        )

    def create_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        title = str(payload.get("title") or "").strip()
        if not title:
            return GitHubTransportResult(ok=False, error="missing_title")
        n = int(payload.get("number") or (abs(hash(repo + "i" + title)) % 9000 + 1))
        return GitHubTransportResult(
            ok=True,
            external_id=f"{repo}#issue-{n}",
            data={"number": n, "title": title, "live": False},
        )

    def comment_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        issue = payload.get("issue_number") or payload.get("number")
        body = str(payload.get("body") or "").strip()
        if issue is None or not body:
            return GitHubTransportResult(ok=False, error="missing_issue_number_or_body")
        cid = f"isc_{uuid4().hex[:8]}"
        return GitHubTransportResult(
            ok=True,
            external_id=cid,
            data={"issue_number": int(issue), "body": body, "live": False},
        )

    def read_repo(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        return GitHubTransportResult(
            ok=True,
            external_id=repo,
            data={"full_name": repo, "default_branch": "main", "live": False},
        )

    def read_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        pr = payload.get("pr_number") or payload.get("number")
        if pr is None:
            return GitHubTransportResult(ok=False, error="missing_pr_number")
        return GitHubTransportResult(
            ok=True,
            external_id=f"{repo}#{pr}",
            data={"number": int(pr), "state": "open", "live": False},
        )

    def list_branches(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        return GitHubTransportResult(
            ok=True,
            external_id=repo,
            data={"branches": ["main", "develop"], "live": False},
        )
