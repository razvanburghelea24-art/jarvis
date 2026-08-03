"""Phase 1C — Command Gateway (single entry, full pipeline, no live exec)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.gateway import (
    ENV_ENABLED,
    CommandGateway,
    PolicyDecisionKind,
    SourceChannel,
    gateway_enabled_from_env,
    reset_command_gateway_for_tests,
)
from src.jarvis.cora_foundation.gateway.audit_hooks import AuditJournal
from src.jarvis.cora_foundation.gateway.pipeline import PIPELINE_STAGES
from src.jarvis.cora_foundation.identity import (
    IdentityService,
    reset_identity_service_for_tests,
)
from src.jarvis.cora_foundation.memory import (
    MemoryEngine,
    reset_memory_engine_for_tests,
)


GW_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "gateway"


@pytest.fixture(autouse=True)
def _reset():
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()
    yield
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert gateway_enabled_from_env() is False


def test_disabled_gateway_still_runs_all_stages(tmp_path):
    identity = IdentityService(enabled=False)
    memory = MemoryEngine(enabled=False, path=tmp_path / "m.json")
    gw = CommandGateway(enabled=False, identity=identity, memory=memory)
    result = gw.submit("whoami", source=SourceChannel.CLI)
    assert result.enabled is False
    assert result.stages_completed == list(PIPELINE_STAGES)
    assert result.response["ok"] is False
    types = [e.event_type for e in gw.audit.events()]
    assert AuditJournal.REQUEST_RECEIVED in types
    assert AuditJournal.REQUEST_FAILED in types


def test_whoami_allowed_dispatches_stub(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    memory.load()
    gw = CommandGateway(enabled=True, identity=identity, memory=memory)
    result = gw.submit("who am I", source=SourceChannel.DESKTOP)
    assert result.stages_completed == list(PIPELINE_STAGES)
    assert result.intent is not None and result.intent.type == "identity.whoami"
    assert result.policy is not None and result.policy.kind == PolicyDecisionKind.ALLOWED
    assert result.dispatch_results and result.dispatch_results[0].ok
    assert result.dispatch_results[0].result.get("stub") is True
    assert result.identity_context.get("owner_id")
    types = [e.event_type for e in gw.audit.events()]
    assert AuditJournal.REQUEST_APPROVED in types
    assert AuditJournal.REQUEST_COMPLETED in types


def test_critical_needs_approval_no_dispatch(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    gw = CommandGateway(enabled=True, identity=identity, memory=memory)
    result = gw.submit("railway deploy", source=SourceChannel.CLI)
    assert result.policy.kind == PolicyDecisionKind.NEEDS_APPROVAL
    assert result.dispatch_results == []
    assert result.plan is not None and result.plan.requires_approval is True
    assert result.response["ok"] is False


def test_e_stop_blocks(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    identity.set_runtime_flags(e_stop=True, current_state="E-Stop")
    memory = MemoryEngine(enabled=False, path=tmp_path / "m.json")
    gw = CommandGateway(enabled=True, identity=identity, memory=memory)
    result = gw.submit("refresh overlay", source=SourceChannel.OVERLAY)
    assert result.policy.kind == PolicyDecisionKind.BLOCKED_E_STOP
    assert result.dispatch_results == []


def test_consumes_memory_context(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    memory.create_task(goal="demo", owner_id=identity.get_owner().owner_id)
    gw = CommandGateway(enabled=True, identity=identity, memory=memory)
    result = gw.submit("list tasks", source=SourceChannel.API)
    assert result.memory_context.get("enabled") is True
    assert result.memory_context.get("task_count") == 1
    assert result.intent.type == "memory.read"
    assert result.policy.kind == PolicyDecisionKind.ALLOWED


def test_capability_registry_names():
    gw = CommandGateway(enabled=False)
    names = set(gw.registry.names())
    for required in {
        "OwnerProfile.read",
        "OwnerProfile.write",
        "Workspace.scan",
        "Discord.send",
        "Overlay.refresh",
        "GitHub.create_pr",
        "Railway.deploy",
        "Server.restart",
        "Memory.read",
        "Memory.write",
        "Identity.whoami",
    }:
        assert required in names


def test_no_live_integration_imports():
    forbidden = {
        "discord",
        "n8n",
        "railway",
        "github",
        "overlay",
        "requests",
        "httpx",
        "aiohttp",
        "daemon",
        "llm",
        "tools",
    }
    for path in GW_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    low = alias.name.lower()
                    for bad in forbidden:
                        assert bad not in low.split("."), f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                # allow relative foundation imports
                if mod.startswith("src.jarvis.cora_foundation") or mod.startswith("."):
                    continue
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"
