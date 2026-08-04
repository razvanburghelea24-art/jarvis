"""Live GitHub transport — real HTTP; phase-gated; injectable request for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .flags import ops_for_phase
from .transport import GitHubTransportResult

HttpFn = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, dict[str, Any]]]


class LiveGitHubTransport:
    """GitHub LIVE — live=True. Ops outside current phase → PHASE_LOCKED."""

    live = True

    def __init__(
        self,
        *,
        token: str,
        phase: int = 1,
        api_base: str = "https://api.github.com",
        http: HttpFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("GitHub LIVE requires a token")
        self._token = token
        self._phase = phase
        self._api_base = api_base.rstrip("/")
        self._http = http or self._default_http
        self._allowed = ops_for_phase(phase)

    def _gate(self, op: str) -> GitHubTransportResult | None:
        if op not in self._allowed:
            return GitHubTransportResult(
                ok=False,
                error="PHASE_LOCKED",
                data={"phase": self._phase, "operation": op},
            )
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Cora-GitHub-LIVE/1",
            "Content-Type": "application/json",
        }

    def _default_http(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: bytes | None,
    ) -> tuple[int, Any]:
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8") or "null"
                data = json.loads(raw) if raw.strip() else {}
                return int(resp.status), data
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"message": raw}
            if isinstance(data, dict):
                data = {**data, "status": exc.code}
            return int(exc.code), data

    def _call(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> GitHubTransportResult:
        url = f"{self._api_base}{path}"
        body = json.dumps(dict(payload or {})).encode("utf-8") if payload is not None else None
        if method == "GET":
            body = None
        status, data = self._http(method, url, self._headers(), body)
        if status >= 400:
            msg = "http_error"
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or f"http_{status}")
            return GitHubTransportResult(
                ok=False,
                error=msg,
                data=data if isinstance(data, dict) else {"raw": data},
            )
        if isinstance(data, list):
            return GitHubTransportResult(ok=True, data={"items": data})
        return GitHubTransportResult(ok=True, data=data if isinstance(data, dict) else {"raw": data})


    def read_repo(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("read_repo")
        if locked:
            return locked
        tr = self._call("GET", f"/repos/{repo}")
        if tr.ok:
            return GitHubTransportResult(
                ok=True,
                external_id=repo,
                data={**(tr.data or {}), "live": True},
            )
        return tr

    def read_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("read_pr")
        if locked:
            return locked
        pr = payload.get("pr_number") or payload.get("number")
        if pr is None:
            return GitHubTransportResult(ok=False, error="missing_pr_number")
        tr = self._call("GET", f"/repos/{repo}/pulls/{int(pr)}")
        if tr.ok:
            return GitHubTransportResult(
                ok=True,
                external_id=f"{repo}#{pr}",
                data={**(tr.data or {}), "live": True},
            )
        return tr

    def list_branches(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("list_branches")
        if locked:
            return locked
        tr = self._call("GET", f"/repos/{repo}/branches")
        if tr.ok:
            items = (tr.data or {}).get("items") or (tr.data or {}).get("branches") or []
            names = [
                (b.get("name") if isinstance(b, dict) else str(b)) for b in items
            ]
            return GitHubTransportResult(
                ok=True,
                external_id=repo,
                data={"branches": names, "live": True},
            )
        return tr

    def create_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("create_issue")
        if locked:
            return locked
        title = str(payload.get("title") or "").strip()
        if not title:
            return GitHubTransportResult(ok=False, error="missing_title")
        body = {
            "title": title,
            "body": str(payload.get("body") or ""),
        }
        tr = self._call("POST", f"/repos/{repo}/issues", body)
        if tr.ok:
            n = (tr.data or {}).get("number")
            return GitHubTransportResult(
                ok=True,
                external_id=f"{repo}#issue-{n}",
                data={**(tr.data or {}), "live": True},
            )
        return tr

    def comment_issue(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("comment_issue")
        if locked:
            return locked
        issue = payload.get("issue_number") or payload.get("number")
        text = str(payload.get("body") or "").strip()
        if issue is None or not text:
            return GitHubTransportResult(ok=False, error="missing_issue_number_or_body")
        tr = self._call(
            "POST",
            f"/repos/{repo}/issues/{int(issue)}/comments",
            {"body": text},
        )
        if tr.ok:
            cid = str((tr.data or {}).get("id") or "")
            return GitHubTransportResult(
                ok=True, external_id=cid, data={**(tr.data or {}), "live": True}
            )
        return tr

    def comment_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("comment_pr")
        if locked:
            return locked
        # PR comments via issues API
        pr = payload.get("pr_number") or payload.get("number")
        text = str(payload.get("body") or "").strip()
        if pr is None or not text:
            return GitHubTransportResult(ok=False, error="missing_pr_number_or_body")
        tr = self._call(
            "POST",
            f"/repos/{repo}/issues/{int(pr)}/comments",
            {"body": text},
        )
        if tr.ok:
            cid = str((tr.data or {}).get("id") or "")
            return GitHubTransportResult(
                ok=True, external_id=cid, data={**(tr.data or {}), "live": True}
            )
        return tr

    def create_pr(self, *, repo: str, payload: Mapping[str, Any]) -> GitHubTransportResult:
        locked = self._gate("create_pr")
        if locked:
            return locked
        title = str(payload.get("title") or "").strip()
        head = str(payload.get("head") or "").strip()
        base = str(payload.get("base") or "main").strip()
        if not title or not head:
            return GitHubTransportResult(ok=False, error="missing_title_or_head")
        body = {
            "title": title,
            "head": head,
            "base": base,
            "body": str(payload.get("body") or ""),
        }
        tr = self._call("POST", f"/repos/{repo}/pulls", body)
        if tr.ok:
            n = (tr.data or {}).get("number")
            return GitHubTransportResult(
                ok=True,
                external_id=f"{repo}#{n}",
                data={**(tr.data or {}), "live": True},
            )
        return tr
