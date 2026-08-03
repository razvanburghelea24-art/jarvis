"""Phase 3 — Integration Hub (READ-ONLY)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.integration import (
    ENV_HUB_ENABLED,
    IntegrationHub,
    IntegrationObject,
    IntegrationSource,
    adapter_enabled,
    get_integration_hub,
    hub_enabled_from_env,
    reset_integration_hub_for_tests,
)
from src.jarvis.cora_foundation.integration.adapters import (
    DiscordAdapter,
    FrameworkAdapter,
    GitHubAdapter,
    N8nAdapter,
    RailwayAdapter,
)
from src.jarvis.cora_foundation.integration.flags import _ADAPTER_ENV


INTEG_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "integration"

_WRITE_VERB_PREFIXES = (
    "write",
    "create",
    "update",
    "delete",
    "patch",
    "post",
    "send",
    "deploy",
    "restart",
    "merge",
    "push",
    "execute",
    "trigger",
    "approve",
    "reject",
    "mute",
    "kick",
    "ban",
)


@pytest.fixture(autouse=True)
def _reset():
    reset_integration_hub_for_tests()
    yield
    reset_integration_hub_for_tests()


def test_hub_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_HUB_ENABLED, raising=False)
    for env_name in _ADAPTER_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    assert hub_enabled_from_env() is False
    assert adapter_enabled("github") is False
    assert get_integration_hub().is_enabled() is False
    assert get_integration_hub().snapshot() == []


def test_adapter_requires_hub_on(monkeypatch):
    monkeypatch.setenv("CORA_ADAPTER_GITHUB_ENABLED", "1")
    monkeypatch.delenv(ENV_HUB_ENABLED, raising=False)
    assert adapter_enabled("github") is False


def test_hub_off_snapshot_empty():
    hub = IntegrationHub(enabled=False)
    hub.enable_adapter("github", True)
    assert hub.snapshot() == []
    assert hub.status()["writes_allowed"] is False


def test_individual_adapter_disable():
    hub = IntegrationHub(enabled=True)
    hub.enable_adapter("github", True)
    hub.enable_adapter("discord", False)
    snap = hub.snapshot()
    sources = {o.source for o in snap}
    assert IntegrationSource.GITHUB in sources
    assert IntegrationSource.DISCORD not in sources
    hub.enable_adapter("github", False)
    assert hub.snapshot() == []


def test_normalize_standard_object():
    hub = IntegrationHub(enabled=True)
    obj = hub.normalize(
        source="github",
        kind="pr",
        title="Fix overlay",
        status="open",
        refs={"repo": "NyMods/overlay", "number": "12"},
        payload={"author": "boss"},
    )
    assert isinstance(obj, IntegrationObject)
    assert obj.read_only is True
    assert obj.source == IntegrationSource.GITHUB
    public = obj.to_public_dict()
    assert public["read_only"] is True
    assert public["kind"] == "pr"
    assert set(public.keys()) >= {
        "object_id",
        "source",
        "kind",
        "title",
        "status",
        "refs",
        "payload",
        "fetched_at",
        "read_only",
    }


def test_github_contract_methods():
    gh = GitHubAdapter(enabled=True)
    assert gh.list_prs()
    assert gh.list_branches()
    assert gh.get_commit(sha="abc123def456") is not None
    assert gh.get_repo_info(repo="owner/repo") is not None
    for o in gh.snapshot():
        assert o.read_only is True
        assert o.source == IntegrationSource.GITHUB


def test_railway_contract_methods():
    rw = RailwayAdapter(enabled=True)
    assert rw.status() is not None
    assert rw.deployments()
    assert rw.logs(deployment_id="d1") is not None
    assert rw.health().payload.get("live") is False


def test_discord_contract_methods():
    dc = DiscordAdapter(enabled=True)
    assert dc.guilds()
    assert dc.channels()
    assert dc.roles()
    assert dc.members()


def test_framework_contract_methods():
    fw = FrameworkAdapter(enabled=True)
    assert fw.status() is not None
    assert fw.players()
    assert fw.weather() is not None
    assert fw.time() is not None
    assert fw.health().payload.get("restart_api") is False


def test_n8n_contract_methods():
    n8 = N8nAdapter(enabled=True)
    assert n8.workflows()
    assert n8.executions()


def test_adapters_have_no_write_methods():
    classes = (GitHubAdapter, RailwayAdapter, DiscordAdapter, FrameworkAdapter, N8nAdapter)
    for cls in classes:
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            lower = name.lower()
            for verb in _WRITE_VERB_PREFIXES:
                # Noun reads like deployments() are allowed; deploy() / deploy_x() are not.
                assert lower != verb, f"{cls.__name__}.{name} is a write verb"
                assert not lower.startswith(verb + "_"), f"{cls.__name__}.{name} looks like a write"


def test_adapters_have_no_owner_or_decide():
    classes = (GitHubAdapter, RailwayAdapter, DiscordAdapter, FrameworkAdapter, N8nAdapter)
    forbidden = {"owner", "decide", "policy", "plan", "agent", "memory_write", "write_memory"}
    for cls in classes:
        names = {n.lower() for n, _ in inspect.getmembers(cls)}
        for bad in forbidden:
            assert bad not in names, f"{cls.__name__} exposes {bad}"


def test_no_network_or_sdk_imports():
    forbidden_mods = {
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "discord",
        "github",
        "railway",
        "n8n",
        "openai",
        "anthropic",
    }
    for path in INTEG_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0].lower()
                    assert root not in forbidden_mods, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative package imports
                mod = (node.module or "").lower()
                if mod.startswith(".") or "cora_foundation" in mod:
                    continue
                root = mod.split(".")[0]
                assert root not in forbidden_mods, f"{path.name} from {mod}"


def test_stub_payloads_mark_not_live():
    hub = IntegrationHub(enabled=True)
    for name in ("github", "railway", "discord", "framework", "n8n"):
        hub.enable_adapter(name, True)
    for obj in hub.snapshot():
        assert obj.read_only is True
        # health + stubs should never claim live writes
        if "live" in obj.payload:
            assert obj.payload["live"] is False


def test_disabled_adapter_returns_empty():
    gh = GitHubAdapter(enabled=False)
    assert gh.list_prs() == []
    assert gh.get_commit(sha="x") is None
    assert gh.snapshot() == []
