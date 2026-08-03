"""GitHub Adapter — READ-ONLY surface."""

from __future__ import annotations

from ..flags import adapter_enabled
from ..types import IntegrationObject, IntegrationSource
from .base import ReadOnlyAdapter


class GitHubAdapter(ReadOnlyAdapter):
    name = "github"
    source = IntegrationSource.GITHUB

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = adapter_enabled("github") if enabled is None else bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def health(self) -> IntegrationObject:
        return self._obj(
            kind="health",
            title="GitHub adapter",
            status="ready" if self._enabled else "disabled",
            payload={"read_only": True, "live": False},
        )

    def list_prs(self, *, repo: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        # Contract-only stub — no live GitHub API in Phase 3.
        return [
            self._obj(
                kind="pr",
                title="(stub) no live fetch",
                status="stub",
                refs={"repo": repo or ""},
                payload={"items": [], "live": False},
            )
        ]

    def list_branches(self, *, repo: str | None = None) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        return [
            self._obj(
                kind="branch",
                title="(stub) no live fetch",
                status="stub",
                refs={"repo": repo or ""},
                payload={"items": [], "live": False},
            )
        ]

    def get_commit(self, *, sha: str, repo: str | None = None) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="commit",
            title=sha[:12] if sha else "(stub)",
            status="stub",
            refs={"repo": repo or "", "sha": sha},
            payload={"live": False},
        )

    def get_repo_info(self, *, repo: str | None = None) -> IntegrationObject | None:
        if not self._enabled:
            return None
        return self._obj(
            kind="repo",
            title=repo or "(stub)",
            status="stub",
            refs={"repo": repo or ""},
            payload={"live": False},
        )

    def snapshot(self) -> list[IntegrationObject]:
        if not self._enabled:
            return []
        out = [self.health()]
        out.extend(self.list_prs())
        out.extend(self.list_branches())
        info = self.get_repo_info()
        if info is not None:
            out.append(info)
        return out
