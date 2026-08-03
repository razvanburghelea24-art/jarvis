"""Phase 1B — Cora Memory SSOT (one API, one adapter, dual-write forbidden)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.memory import (
    ENV_ENABLED,
    JsonStorageAdapter,
    MemoryEngine,
    MemoryKind,
    TaskStatus,
    get_memory_engine,
    memory_enabled_from_env,
    reset_memory_engine_for_tests,
)


MEMORY_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "cora_foundation" / "memory"


@pytest.fixture(autouse=True)
def _reset():
    reset_memory_engine_for_tests()
    yield
    reset_memory_engine_for_tests()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_ENABLED, raising=False)
    assert memory_enabled_from_env() is False


def test_disabled_engine_is_inert(tmp_path):
    path = tmp_path / "cora_memory_ssot.json"
    eng = MemoryEngine(enabled=False, path=path)
    assert eng.put_owner_memory(owner_id="own_x") is None
    assert eng.create_task(goal="x") is None
    assert eng.list() == []
    assert path.exists() is False
    snap = eng.snapshot()
    assert snap["enabled"] is False
    assert snap["record_count"] == 0


def test_single_ssot_file_and_versioning(tmp_path):
    path = tmp_path / "cora_memory_ssot.json"
    eng = MemoryEngine(enabled=True, path=path)

    owner = eng.put_owner_memory(
        owner_id="own_1",
        preferences={"tone": "direct"},
        rules=["owner-only commands"],
    )
    assert owner is not None
    assert owner.version == 1
    assert owner.record_id == "owner_own_1"

    owner2 = eng.put_owner_memory(
        owner_id="own_1",
        preferences={"tone": "calm"},
        rules=["owner-only commands"],
    )
    assert owner2 is not None and owner2.version == 2

    ses = eng.put_session_memory(session_id="ses_1", conversation=[{"role": "user", "text": "hi"}])
    ws = eng.put_workspace_memory(
        workspace_id="ws_1",
        repository="https://example/repo",
        branch="feature/x",
        worktree=str(tmp_path),
    )
    rt = eng.put_runtime_memory(runtime_id="rt_1", current_state="Thinking")
    task = eng.create_task(goal="ship 1B", owner_id="own_1", dependencies=[])
    assert all(x is not None for x in (ses, ws, rt, task))

    # Exactly one SSOT file — not four JSON stores.
    json_files = list(tmp_path.glob("*.json"))
    assert json_files == [path]

    eng.append_task_log(task.record_id, "started foundation memory")
    eng.update_task_status(task.record_id, TaskStatus.IN_PROGRESS)
    again = eng.get(task.record_id)
    assert again is not None
    assert again.version >= 3
    assert again.payload["status"] == TaskStatus.IN_PROGRESS.value
    assert "started foundation memory" in again.payload["logs"]

    kinds = {r.kind for r in eng.list()}
    assert kinds == {
        MemoryKind.OWNER,
        MemoryKind.SESSION,
        MemoryKind.WORKSPACE,
        MemoryKind.RUNTIME,
        MemoryKind.TASK,
    }


def test_restart_reconstruction(tmp_path):
    path = tmp_path / "cora_memory_ssot.json"
    eng1 = MemoryEngine(enabled=True, path=path)
    t = eng1.create_task(goal="survive restart", owner_id="own_z")
    assert t is not None
    tid = t.record_id
    eng1.put_runtime_memory(runtime_id="rt_z", current_state="Idle", safe_mode=False)

    # New engine instance = process restart simulation
    eng2 = MemoryEngine(enabled=True, path=path)
    n = eng2.load()
    assert n >= 2
    restored = eng2.get(tid)
    assert restored is not None
    assert restored.payload["goal"] == "survive restart"
    assert restored.kind == MemoryKind.TASK


def test_unique_task_ids(tmp_path):
    eng = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    t1 = eng.create_task(goal="a")
    t2 = eng.create_task(goal="b")
    assert t1 is not None and t2 is not None
    assert t1.record_id != t2.record_id
    assert t1.payload["task_id"] != t2.payload["task_id"]


def test_no_forbidden_imports():
    forbidden = {
        "owner_profile",
        "daemon",
        "brain_v3",
        "tools",
        "devmode",
        "llm",
        "reply",
        "discord",
        "overlay",
        "redis",
        "sqlite3",
    }
    for path in MEMORY_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden:
                        assert bad not in alias.name.lower(), f"{path.name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                for bad in forbidden:
                    assert bad not in mod.split("."), f"{path.name}: from {mod}"


def test_singleton_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_ENABLED, "true")
    monkeypatch.setenv("JARVIS_CONFIG_PATH", str(tmp_path / "config.json"))
    reset_memory_engine_for_tests()
    eng = get_memory_engine()
    assert eng.enabled is True
    eng.create_task(goal="via singleton")
    assert (tmp_path / "cora_memory_ssot.json").exists()
