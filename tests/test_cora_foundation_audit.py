"""Phase 1D — Audit Engine (append-only, redaction, request reconstruction)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.audit import (
    ENV_ENABLED,
    AppendOnlyLogAdapter,
    AuditEngine,
    AuditEventType,
    audit_enabled_from_env,
    get_audit_engine,
    redact_value,
    reset_audit_engine_for_tests,
)
from src.jarvis.cora_foundation.gateway import CommandGateway, SourceChannel, reset_command_gateway_for_tests
from src.jarvis.cora_foundation.identity import IdentityService, reset_identity_service_for_tests
from src.jarvis.cora_foundation.memory import MemoryEngine, reset_memory_engine_for_tests


AUDIT_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "audit"


@pytest.fixture(autouse=True)
def _reset():
    reset_audit_engine_for_tests()
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()
    yield
    reset_audit_engine_for_tests()
    reset_command_gateway_for_tests()
    reset_identity_service_for_tests()
    reset_memory_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert audit_enabled_from_env() is False


def test_disabled_audit_writes_nothing(tmp_path):
    path = tmp_path / "audit.log"
    eng = AuditEngine(enabled=False, path=path)
    assert eng.append(event_type=AuditEventType.REQUEST_RECEIVED, request_id="cmd_x") is None
    assert path.exists() is False


def test_append_only_and_reconstruct(tmp_path):
    path = tmp_path / "audit.log"
    eng = AuditEngine(enabled=True, path=path)
    rid = "cmd_abc"
    eng.append(event_type=AuditEventType.REQUEST_RECEIVED, request_id=rid, source="cli", status="received")
    eng.append(event_type=AuditEventType.INTENT_CLASSIFIED, request_id=rid, intent_id="int_1", status="classified")
    eng.append(event_type=AuditEventType.REQUEST_COMPLETED, request_id=rid, status="completed", duration_ms=12.5)

    # Second request
    eng.append(event_type=AuditEventType.REQUEST_RECEIVED, request_id="cmd_other", status="received")

    flow = eng.for_request(rid)
    assert [e.event_type for e in flow] == [
        AuditEventType.REQUEST_RECEIVED,
        AuditEventType.INTENT_CLASSIFIED,
        AuditEventType.REQUEST_COMPLETED,
    ]
    assert all(e.request_id == rid for e in flow)
    # Unique schema fields present
    e0 = flow[0]
    for field in (
        "event_id",
        "timestamp",
        "session_id",
        "owner_id",
        "workspace_id",
        "request_id",
        "intent_id",
        "event_type",
        "status",
        "source",
        "capability",
        "risk_level",
        "duration_ms",
        "result",
        "metadata",
    ):
        assert field in e0.to_dict()

    # Append-only: file grows; no rewrite API
    lines1 = path.read_text(encoding="utf-8").strip().splitlines()
    eng.append(event_type=AuditEventType.REQUEST_FAILED, request_id=rid, status="failed")
    lines2 = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == len(lines1) + 1
    assert lines2[: len(lines1)] == lines1


def test_redacts_secrets():
    payload = {
        "Authorization": "Bearer SUPERSECRETTOKEN",
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz",
        "nested": {"password": "hunter2", "ok": "visible"},
        "note": "bearer ghp_abcdefghijklmnopqrstuvwx",
    }
    cleaned = redact_value(payload)
    assert cleaned["Authorization"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["password"] == "[REDACTED]"
    assert cleaned["nested"]["ok"] == "visible"
    assert "[REDACTED]" in cleaned["note"]


def test_estop_helpers(tmp_path):
    eng = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    a = eng.emit_estop_triggered("cmd_stop", owner_id="own_1")
    b = eng.emit_estop_released("cmd_stop", owner_id="own_1")
    assert a is not None and a.event_type == AuditEventType.ESTOP_TRIGGERED
    assert b is not None and b.event_type == AuditEventType.ESTOP_RELEASED


def test_gateway_persists_full_trail_when_audit_on(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    audit = AuditEngine(enabled=True, path=tmp_path / "audit.log")
    gw = CommandGateway(enabled=True, identity=identity, memory=memory, audit_engine=audit)
    result = gw.submit("who am I", source=SourceChannel.DESKTOP)
    assert result.response["ok"] is True

    flow = audit.for_request(result.command_id)
    types = [e.event_type for e in flow]
    assert AuditEventType.REQUEST_RECEIVED in types
    assert AuditEventType.REQUEST_NORMALIZED in types
    assert AuditEventType.IDENTITY_RESOLVED in types
    assert AuditEventType.MEMORY_RESOLVED in types
    assert AuditEventType.INTENT_CLASSIFIED in types
    assert AuditEventType.POLICY_EVALUATED in types
    assert AuditEventType.PLAN_CREATED in types
    assert AuditEventType.DISPATCH_STARTED in types
    assert AuditEventType.DISPATCH_COMPLETED in types
    assert AuditEventType.REQUEST_COMPLETED in types


def test_no_update_or_delete_methods_on_adapter():
    names = {m for m in dir(AppendOnlyLogAdapter) if not m.startswith("_")}
    assert "append" in names and "read_all" in names
    assert "update" not in names and "delete" not in names and "rewrite" not in names


def test_no_forbidden_imports():
    forbidden = {"discord", "n8n", "daemon", "llm", "tools", "sqlite3", "redis"}
    for path in AUDIT_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if mod.startswith(".") or "cora_foundation" in mod:
                    continue
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name} from {mod}"
