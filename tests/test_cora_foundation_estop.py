"""Phase 1E — Emergency Stop (industrial safety gate)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.audit import AuditEngine, AuditEventType, reset_audit_engine_for_tests
from src.jarvis.cora_foundation.emergency_stop import (
    ENV_ENABLED,
    EmergencyStopEngine,
    SafetyMode,
    TriggerSource,
    estop_enabled_from_env,
    get_emergency_stop,
    reset_emergency_stop_for_tests,
)
from src.jarvis.cora_foundation.gateway import (
    CommandGateway,
    PolicyDecisionKind,
    SourceChannel,
    reset_command_gateway_for_tests,
)
from src.jarvis.cora_foundation.identity import IdentityService, reset_identity_service_for_tests
from src.jarvis.cora_foundation.memory import MemoryEngine, reset_memory_engine_for_tests


ESTOP_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "emergency_stop"


@pytest.fixture(autouse=True)
def _reset():
    reset_emergency_stop_for_tests()
    reset_audit_engine_for_tests()
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()
    yield
    reset_emergency_stop_for_tests()
    reset_audit_engine_for_tests()
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert estop_enabled_from_env() is False


def test_module_off_does_not_enforce(tmp_path):
    eng = EmergencyStopEngine(enabled=False, path=tmp_path / "safety.json")
    out = eng.trigger(reason="test", trigger=TriggerSource.OWNER)
    assert out["accepted"] is False
    assert eng.allows_capability("Discord.send") is True


def test_persist_across_restart(tmp_path):
    path = tmp_path / "safety.json"
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    eng = EmergencyStopEngine(enabled=True, path=path, audit=audit)
    eng.load()
    eng.trigger(mode=SafetyMode.ESTOP_MANUAL, reason="manual halt", trigger=TriggerSource.OWNER, request_id="cmd_1")
    assert eng.current_mode() == SafetyMode.ESTOP_MANUAL

    eng2 = EmergencyStopEngine(enabled=True, path=path, audit=audit)
    assert eng2.load() == SafetyMode.ESTOP_MANUAL
    assert eng2.snapshot()["is_estop"] is True
    assert "Emergency Stop" in eng2.status_message()


def test_whoami_allowed_discord_blocked(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    estop = EmergencyStopEngine(enabled=True, path=tmp_path / "safety.json", audit=audit)
    estop.load()
    estop.trigger(reason="owner stop", trigger=TriggerSource.OWNER, request_id="cmd_trig")

    gw = CommandGateway(
        enabled=True,
        identity=identity,
        memory=memory,
        audit_engine=audit,
        emergency_stop=estop,
    )
    ok = gw.submit("who am I", source=SourceChannel.DESKTOP)
    assert ok.response["ok"] is True
    assert ok.dispatch_results and ok.dispatch_results[0].ok

    blocked = gw.submit("send discord hello", source=SourceChannel.DISCORD)
    assert blocked.response["ok"] is False
    assert blocked.policy.kind == PolicyDecisionKind.BLOCKED_E_STOP
    assert blocked.dispatch_results == []


def test_only_owner_release_audited(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    estop = EmergencyStopEngine(enabled=True, path=tmp_path / "safety.json", audit=audit)
    estop.load()
    estop.trigger(reason="halt", trigger=TriggerSource.WATCHDOG, request_id="cmd_a")
    with pytest.raises(PermissionError):
        estop.release(owner_id="")
    out = estop.release(owner_id="own_boss", reason="all clear", request_id="cmd_rel")
    assert out["mode"] == SafetyMode.NORMAL.value
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.ESTOP_TRIGGERED in types
    assert AuditEventType.ESTOP_RELEASED in types


def test_safe_mode_events(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    estop = EmergencyStopEngine(enabled=True, path=tmp_path / "safety.json", audit=audit)
    estop.load()
    estop.enter_safe_mode(reason="caution", trigger=TriggerSource.POLICY, request_id="cmd_sm")
    assert estop.current_mode() == SafetyMode.SAFE_MODE
    assert estop.allows_capability("Memory.read") is True
    assert estop.allows_capability("Railway.deploy") is False
    estop.exit_safe_mode(request_id="cmd_sm_exit")
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.SAFE_MODE_ENTERED in types
    assert AuditEventType.SAFE_MODE_EXITED in types


def test_unified_trigger_sources(tmp_path):
    estop = EmergencyStopEngine(enabled=True, path=tmp_path / "safety.json")
    estop.load()
    for src in (TriggerSource.OWNER, TriggerSource.POLICY, TriggerSource.SENTINEL, TriggerSource.RUNTIME, TriggerSource.WATCHDOG):
        reset_emergency_stop_for_tests()
        e = EmergencyStopEngine(enabled=True, path=tmp_path / f"s_{src.value}.json")
        e.load()
        e.trigger(reason=f"from {src.value}", trigger=src)
        assert e.snapshot()["trigger"] == src.value


def test_no_forbidden_imports():
    forbidden = {"discord", "n8n", "daemon", "llm", "tools", "requests"}
    for path in ESTOP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if mod.startswith(".") or "cora_foundation" in mod:
                    continue
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"
