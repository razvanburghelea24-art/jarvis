"""Isolation between H Phase 1 plan-only and Brain Memory v2 (both default OFF)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.config import get_default_config
from jarvis.development.owner_development import (
    _LAST_PLAN,
    _PENDING,
    try_owner_development_command,
)
from jarvis.memory.brain_v2 import create_brain_memory_v2


class _DM:
    pass


@pytest.mark.unit
def test_both_flags_off_inactive(tmp_path):
    cfg = SimpleNamespace(owner_triggered_development_enabled=False, self_eval_enabled=True)
    dm = _DM()
    r = try_owner_development_command(
        "Cora, prepare an implementation plan for hashing",
        cfg=cfg,
        dialogue_memory=dm,
        backend=None,
        actor="owner",
    )
    assert r.handled is False
    assert create_brain_memory_v2(enabled=False, root_dir=tmp_path) is None
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.unit
def test_h_harness_on_brain_off_zero_bv2_io(tmp_path):
    from jarvis.development.models import CANONICAL_WORKSPACE_ROOT
    from jarvis.development.read_only_backend import FakeReadOnlyBackend

    be = FakeReadOnlyBackend(
        root=CANONICAL_WORKSPACE_ROOT,
        branch="feature/cora-f-real-search-clean",
        head_sha="a" * 40,
        working_tree_clean=True,
        files={
            "src/jarvis/x.py": "x=1\n",
            "tests/test_x.py": "def test_x():\n    assert True\n",
        },
    )
    cfg = SimpleNamespace(
        owner_triggered_development_enabled=True,
        self_eval_enabled=True,
        _h_dev_backend=be,
    )
    dm = _DM()
    r1 = try_owner_development_command(
        "Cora, prepare an implementation plan for hashing helper",
        cfg=cfg,
        dialogue_memory=dm,
        backend=be,
        actor="owner",
        consult_g=False,
    )
    assert r1.handled is True
    assert getattr(dm, _PENDING, None) is not None
    assert create_brain_memory_v2(enabled=False, root_dir=tmp_path) is None
    assert not (tmp_path / "preferences.json").exists()
    r2 = try_owner_development_command(
        "da",
        cfg=cfg,
        dialogue_memory=dm,
        backend=be,
        actor="owner",
        consult_g=False,
    )
    assert r2.handled is True
    plan = getattr(dm, _LAST_PLAN, None)
    assert plan is not None
    assert plan.applied_changes is False
    assert not (tmp_path / "projects.json").exists()


@pytest.mark.unit
def test_brain_on_h_off_no_h_pending(tmp_path):
    cfg = SimpleNamespace(owner_triggered_development_enabled=False)
    dm = _DM()
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    brain.preference.propose("tone", "concise")
    brain.project.create("p1", "P1")
    r = try_owner_development_command(
        "Cora, prepare an implementation plan for X",
        cfg=cfg,
        dialogue_memory=dm,
        backend=None,
        actor="owner",
    )
    assert r.handled is False
    assert getattr(dm, _PENDING, None) is None
    assert brain.preference.get("tone") is not None


@pytest.mark.unit
def test_h_plan_not_saved_in_project_memory(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert list(brain.project.list()) == []
    assert brain.project.get_active() is None


@pytest.mark.unit
def test_flags_independent_in_defaults():
    d = get_default_config()
    assert d["brain_memory_v2_enabled"] is False
    assert d["owner_triggered_development_enabled"] is False


@pytest.mark.unit
def test_brain_package_has_no_h_activation():
    import jarvis.memory.brain_v2 as bv2

    root = Path(bv2.__file__).parent
    for p in root.glob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "owner_triggered_development_enabled" not in t
        assert "subprocess" not in t
