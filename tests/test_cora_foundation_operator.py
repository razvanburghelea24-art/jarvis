"""Phase 6A — Computer Operator Observability (no control)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.audit import (
    AuditEngine,
    AuditEventType,
    reset_audit_engine_for_tests,
)
from src.jarvis.cora_foundation.computer_operator import (
    ENV_CONTROL_ENABLED,
    ENV_ENABLED,
    AppAllowlist,
    ComputerOperator,
    IndicatorState,
    get_computer_operator,
    operator_control_enabled_from_env,
    operator_enabled_from_env,
    reset_computer_operator_for_tests,
)
from src.jarvis.cora_foundation.emergency_stop import (
    EmergencyStopEngine,
    TriggerSource,
    reset_emergency_stop_for_tests,
)


OP_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "computer_operator"


@pytest.fixture(autouse=True)
def _reset():
    reset_computer_operator_for_tests()
    reset_audit_engine_for_tests()
    reset_emergency_stop_for_tests()
    yield
    reset_computer_operator_for_tests()
    reset_audit_engine_for_tests()
    reset_emergency_stop_for_tests()


def test_flags_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    monkeypatch.delenv(ENV_CONTROL_ENABLED, raising=False)
    assert operator_enabled_from_env() is False
    assert operator_control_enabled_from_env() is False
    assert get_computer_operator().observe() is None


def test_observe_snapshot_no_controls(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    op = ComputerOperator(enabled=True, control_enabled=False, audit=audit, clipboard_permitted=True)
    snap = op.observe()
    assert snap is not None
    assert snap.controls is False
    assert snap.live is False
    assert snap.active_app == "VS Code"
    assert snap.mouse_position is not None
    assert snap.keyboard_idle is True
    assert snap.clipboard_preview is not None
    assert snap.windows
    assert snap.processes
    assert snap.monitors
    assert op.indicator() == IndicatorState.OBSERVE
    public = snap.to_public_dict()
    assert public["controls"] is False
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.OPERATOR_OBSERVE in types


def test_clipboard_not_permitted_by_default():
    op = ComputerOperator(enabled=True, clipboard_permitted=False)
    snap = op.observe()
    assert snap is not None
    assert snap.clipboard_preview is None


def test_control_methods_denied(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    op = ComputerOperator(enabled=True, control_enabled=False, audit=audit)
    for method in ("click", "type_keys", "move_mouse", "open_app", "close_app", "write_clipboard", "automate"):
        out = getattr(op, method)()
        assert out["accepted"] is False
        assert out["executed"] is False
    assert AuditEventType.OPERATOR_DENIED in [e.event_type for e in audit.read_all()]


def test_control_flag_still_cannot_bypass_pipeline(tmp_path):
    """Even with control flag ON, direct control calls are denied in 6A surface."""
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    op = ComputerOperator(enabled=True, control_enabled=True, audit=audit)
    out = op.click(x=10, y=10)
    assert out["accepted"] is False
    assert out["reason"] == "must_use_planner_scheduler_policy_dispatcher"


def test_action_preview_waiting_owner(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    op = ComputerOperator(enabled=True, audit=audit)
    preview = op.create_preview(
        title="Edit file",
        steps=[
            {"description": "Open VS Code", "target_app": "VS Code", "capability": "Computer.open_app"},
            {"description": "Click line 42", "target_app": "VS Code", "capability": "Computer.click"},
            {"description": "Paste code", "target_app": "VS Code", "capability": "Computer.type_keys"},
        ],
    )
    assert preview is not None
    assert "Cora intends to:" in preview.render_prompt()
    assert "YES / NO" in preview.render_prompt()
    assert preview.executable is False
    assert op.indicator() == IndicatorState.WAITING_OWNER
    approved = op.approve_preview(preview.preview_id, owner_id="own_boss")
    assert approved is not None
    assert approved.status.value == "APPROVED"
    assert approved.executable is False
    # Still cannot execute
    denied = op.execute_preview(preview.preview_id)
    assert denied["executed"] is False
    types = [e.event_type for e in audit.read_all()]
    assert AuditEventType.OPERATOR_PREVIEW in types
    assert AuditEventType.OPERATOR_APPROVED in types
    assert AuditEventType.OPERATOR_DENIED in types


def test_preview_allowlist_deny(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    op = ComputerOperator(enabled=True, audit=audit)
    preview = op.create_preview(
        title="Bad",
        steps=[{"description": "Open banking", "target_app": "BankApp"}],
    )
    assert preview is not None
    assert preview.status.value == "DENIED"
    assert AuditEventType.OPERATOR_DENIED in [e.event_type for e in audit.read_all()]


def test_allowlist_default_apps():
    al = AppAllowlist()
    assert al.is_allowed("VS Code")
    assert al.is_allowed("Blender")
    assert al.is_allowed("Chrome")
    assert not al.is_allowed("BankApp")
    assert "DENY" in (al.deny_reason("BankApp") or "")


def test_estop_interrupt_cancels_previews(tmp_path):
    audit = AuditEngine(enabled=True, path=tmp_path / "a.log")
    estop = EmergencyStopEngine(enabled=True, path=tmp_path / "safety.json", audit=audit)
    estop.load()
    op = ComputerOperator(enabled=True, audit=audit, estop=estop)
    preview = op.create_preview(
        title="Act",
        steps=[{"description": "Open VS Code", "target_app": "VS Code"}],
    )
    assert preview is not None
    estop.trigger(reason="halt", trigger=TriggerSource.OWNER)
    op.interrupt(reason="estop")
    assert op.indicator() == IndicatorState.OBSERVE
    assert AuditEventType.OPERATOR_CANCELLED in [e.event_type for e in audit.read_all()]
    # Control still denied under estop
    assert op.click()["reason"] in {"estop", "control_disabled_phase_6a", "must_use_planner_scheduler_policy_dispatcher"}


def test_status_never_bypasses_brain():
    op = ComputerOperator(enabled=True)
    st = op.status()
    assert st["decides"] is False
    assert st["bypasses_planner"] is False
    assert st["bypasses_scheduler"] is False
    assert st["bypasses_policy"] is False
    assert st["control_enabled"] is False
    assert st["mode"] == "observability"


def test_no_gui_automation_imports():
    forbidden = {"pyautogui", "pynput", "keyboard", "mouse", "win32api", "ctypes"}
    for path in OP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0].lower() not in forbidden
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                mod = (node.module or "").split(".")[0].lower()
                assert mod not in forbidden
