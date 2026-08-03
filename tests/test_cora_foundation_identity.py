"""Phase 1A — Cora Foundation Identity (independent, default OFF, no business logic)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.identity import (
    AccessLevel,
    IdentityService,
    SessionState,
    WorkspaceMode,
    get_identity_service,
    reset_identity_service_for_tests,
    whoami,
)
from src.jarvis.cora_foundation.identity.flags import ENV_ENABLED, identity_enabled_from_env


ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DIR = ROOT / "src" / "jarvis" / "cora_foundation" / "identity"


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_identity_service_for_tests()
    yield
    reset_identity_service_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert identity_enabled_from_env() is False


def test_flag_explicit_on(monkeypatch):
    monkeypatch.setenv(ENV_ENABLED, "true")
    assert identity_enabled_from_env() is True


def test_disabled_service_returns_empty_snapshot():
    svc = IdentityService(enabled=False)
    assert svc.ensure_owner() is None
    assert svc.start_session() is None
    assert svc.set_workspace(path="/tmp/x") is None
    assert svc.ensure_runtime() is None
    snap = svc.snapshot()
    assert snap.enabled is False
    assert snap.owner is None
    assert snap.session is None
    d = snap.to_public_dict()
    assert d["who"] is None
    assert d["active_session"] is None


def test_enabled_bootstrap_answers_who_where_session():
    svc = IdentityService(enabled=True)
    snap = svc.bootstrap_minimal()
    assert snap.enabled is True
    assert snap.owner is not None and snap.owner.owner_id.startswith("own_")
    assert snap.session is not None and snap.session.session_id.startswith("ses_")
    assert snap.workspace is not None and snap.workspace.workspace_id.startswith("ws_")
    assert snap.runtime is not None and snap.runtime.runtime_id.startswith("rt_")
    assert snap.runtime.core_name == "cora-core"
    assert snap.owner.access_level == AccessLevel.OWNER
    assert snap.owner.auth_key_id is not None
    assert "secret" not in snap.owner.auth_key_id  # id reference only

    public = whoami(svc)
    assert public["who"] == snap.owner.owner_id
    assert public["active_session"] == snap.session.session_id
    assert public["where"]["workspace_id"] == snap.workspace.workspace_id
    assert public["who_are_you"]["runtime_id"] == snap.runtime.runtime_id
    assert public["who_are_you"]["e_stop"] is False
    assert public["who_are_you"]["safe_mode"] is False


def test_workspace_and_session_state_updates():
    svc = IdentityService(enabled=True)
    svc.bootstrap_minimal()
    ws = svc.set_workspace(
        path=r"C:\Users\Administrator\cora-wt-foundation-1a-identity",
        repository="https://github.com/isair/jarvis.git",
        branch="feature/cora-foundation-1a-identity",
        head="4f49876",
        mode=WorkspaceMode.DEV,
    )
    assert ws is not None
    assert ws.mode == WorkspaceMode.DEV
    assert ws.branch.endswith("1a-identity")

    ses = svc.set_session_state(SessionState.THINKING)
    assert ses is not None and ses.state == SessionState.THINKING

    svc.set_runtime_flags(safe_mode=True, e_stop=False, current_state="SafeMode")
    rt = svc.get_runtime()
    assert rt is not None and rt.safe_mode is True and rt.current_state == "SafeMode"


def test_singleton_respects_env(monkeypatch):
    monkeypatch.setenv(ENV_ENABLED, "1")
    reset_identity_service_for_tests()
    svc = get_identity_service()
    assert svc.enabled is True
    svc.bootstrap_minimal()
    assert whoami()["enabled"] is True


def test_no_business_imports_in_identity_package():
    """Identity must not import Memory/Gateway/tools/Discord/Overlay/owner_profile/daemon."""
    forbidden = {
        "owner_profile",
        "daemon",
        "memory",
        "brain_v3",
        "tools",
        "devmode",
        "development",
        "llm",
        "reply",
    }
    for path in IDENTITY_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden:
                        assert bad not in alias.name, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"
                    for alias in node.names:
                        assert bad not in alias.name, f"{path.name} imports name {alias.name}"


def test_unique_ids_across_bootstraps():
    a = IdentityService(enabled=True)
    b = IdentityService(enabled=True)
    sa = a.bootstrap_minimal()
    sb = b.bootstrap_minimal()
    assert sa.owner.owner_id != sb.owner.owner_id
    assert sa.session.session_id != sb.session.session_id
    assert sa.workspace.workspace_id != sb.workspace.workspace_id
    assert sa.runtime.runtime_id != sb.runtime.runtime_id
