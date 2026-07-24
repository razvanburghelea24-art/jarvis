"""Isolation / architecture tests for Brain Memory v2 Preference+Project slice.

Runs only against temporary directories. Never touches live ~/.config/jarvis.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from jarvis.memory.brain_v2 import create_brain_memory_v2
from jarvis.memory.brain_v2.models import (
    PreferenceMemoryRecord,
    ProjectMemoryRecord,
)
from jarvis.memory.brain_v2.paths import default_brain_v2_root, safe_store_path
from jarvis.memory.brain_v2.persistence import BrainV2JsonStore, DEFAULT_MAX_BACKUPS
from jarvis.memory.brain_v2.models import empty_preferences_document
from jarvis.utils.redact import scrub_secrets


@pytest.mark.unit
def test_01_flag_off_zero_io(tmp_path):
    assert create_brain_memory_v2(enabled=False, root_dir=tmp_path) is None
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.unit
def test_02_import_zero_io(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_CONFIG_PATH", str(tmp_path / "config.json"))
    # Re-import paths helper and ensure default root is under tmp via env.
    import jarvis.memory.brain_v2 as pkg
    importlib.reload(pkg)
    before = {p for p in tmp_path.rglob("*")}
    # Importing submodules must not create brain_v2 dirs.
    import jarvis.memory.brain_v2.preference  # noqa: F401
    import jarvis.memory.brain_v2.project  # noqa: F401
    import jarvis.memory.brain_v2.persistence  # noqa: F401
    after = {p for p in tmp_path.rglob("*")}
    assert before == after
    assert not (tmp_path / "memory").exists()


@pytest.mark.unit
def test_03_to_07_preference_lifecycle(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain.preference.propose("tone", "concise").confirmed is False
    assert brain.preference.confirm("tone").confirmed is True
    assert brain.preference.get("tone").value == "concise"
    assert any(r.key == "tone" for r in brain.preference.list())
    assert brain.preference.reject("tone") is True
    assert brain.preference.get("tone") is None
    assert brain.preference.delete("missing") is True  # idempotent
    assert brain.preference.confirm("missing") is None  # fail-safe


@pytest.mark.unit
def test_08_corrupt_primary_valid_bak(tmp_path):
    primary = tmp_path / "preferences.json"
    bak = tmp_path / "preferences.json.bak"
    good = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "items": {"k": PreferenceMemoryRecord(key="k", value="from-bak").to_dict()},
    }
    bak.write_text(json.dumps(good), encoding="utf-8")
    primary.write_text("{broken", encoding="utf-8")
    store = BrainV2JsonStore(
        primary, empty_factory=empty_preferences_document, backups_dir=tmp_path / "backups", writable=True
    )
    assert store.snapshot()["items"]["k"]["value"] == "from-bak"


@pytest.mark.unit
def test_09_corrupt_primary_bak_valid_timestamped(tmp_path):
    primary = tmp_path / "preferences.json"
    bak = tmp_path / "preferences.json.bak"
    backups = tmp_path / "backups"
    backups.mkdir()
    good = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "items": {"k": PreferenceMemoryRecord(key="k", value="from-ts").to_dict()},
    }
    (backups / "preferences-20260101T000000Z.json").write_text(json.dumps(good), encoding="utf-8")
    primary.write_text("!!!", encoding="utf-8")
    bak.write_text("!!!", encoding="utf-8")
    store = BrainV2JsonStore(
        primary, empty_factory=empty_preferences_document, backups_dir=backups, writable=True
    )
    assert store.snapshot()["items"]["k"]["value"] == "from-ts"


@pytest.mark.unit
def test_10_all_corrupt_empty(tmp_path):
    primary = tmp_path / "preferences.json"
    primary.write_text("x", encoding="utf-8")
    (tmp_path / "preferences.json.bak").write_text("y", encoding="utf-8")
    store = BrainV2JsonStore(
        primary, empty_factory=empty_preferences_document, backups_dir=tmp_path / "backups", writable=True
    )
    assert store.snapshot()["items"] == {}


@pytest.mark.unit
def test_11_storage_unavailable_memory_only(tmp_path):
    with mock.patch(
        "jarvis.memory.brain_v2.facade._durable_pref_proj",
        side_effect=OSError("unavailable"),
    ):
        brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    assert brain.storage_ok is False
    assert brain.preference.propose("a", "b") is not None
    assert not (tmp_path / "preferences.json").exists()


@pytest.mark.unit
def test_12_atomic_write_failure(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    with mock.patch(
        "jarvis.memory.brain_v2.persistence.atomic_write_text",
        side_effect=OSError("disk full"),
    ):
        assert brain.preference.propose("z", "nope") is None


@pytest.mark.unit
def test_13_two_threads_preference(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    err: list[BaseException] = []

    def w(i: int) -> None:
        try:
            brain.preference.propose(f"p{i}", str(i))
            brain.preference.confirm(f"p{i}")
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    ts = [threading.Thread(target=w, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert err == []
    assert len(brain.preference.list()) == 2


@pytest.mark.unit
def test_14_two_threads_project(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    err: list[BaseException] = []

    def w(i: int) -> None:
        try:
            brain.project.create(f"proj{i}", f"P{i}")
            brain.project.update_next_action(f"proj{i}", f"step{i}")
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    ts = [threading.Thread(target=w, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert err == []
    assert len(brain.project.list()) == 2


@pytest.mark.unit
def test_15_to_19_project_ops(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain.project.create("alpha", "Alpha", summary="s") is not None
    assert brain.project.create("beta", "Beta") is not None
    assert brain.project.set_active("beta") is True
    assert brain.project.get_active() == "beta"
    assert brain.project.update_status("beta", "paused").status == "paused"
    assert brain.project.update_next_action("beta", "do-x", last_action="did-y").next_action == "do-x"
    assert brain.project.archive("beta") is True
    assert brain.project.get_active() is None
    assert brain.project.set_active("beta") is False


@pytest.mark.unit
def test_20_invalid_metadata_dropped():
    rec = ProjectMemoryRecord.from_dict(
        {
            "project_id": "m1",
            "name": "M",
            "metadata": {"ok": "yes", "bad": object()},
        }
    )
    dumped = rec.to_dict()
    assert dumped["metadata"].get("ok") == "yes"
    assert "bad" not in dumped["metadata"]


@pytest.mark.unit
def test_21_oversized_payload_clamped():
    huge = "x" * 50_000
    rec = PreferenceMemoryRecord.from_dict({"key": "k", "value": huge})
    assert len(rec.value) <= 4000
    meta_huge = {"blob": "y" * 10_000}
    proj = ProjectMemoryRecord.from_dict({"project_id": "p", "name": "P", "metadata": meta_huge})
    assert "blob" not in proj.to_dict()["metadata"] or len(json.dumps(proj.to_dict()["metadata"])) <= 4000


@pytest.mark.unit
def test_22_invalid_schema_version_normalized():
    pref = PreferenceMemoryRecord.from_dict({"key": "k", "value": "v", "schema_version": "nope"})
    assert pref.schema_version == 1
    pref2 = PreferenceMemoryRecord.from_dict({"key": "k", "value": "v", "schema_version": 0})
    assert pref2.schema_version == 1


@pytest.mark.unit
def test_23_timestamps_utc_z():
    rec = PreferenceMemoryRecord(key="k", value="v")
    assert rec.created_at.endswith("Z")
    assert "T" in rec.created_at


@pytest.mark.unit
def test_24_25_path_fix_and_no_traversal(tmp_path):
    p = safe_store_path(tmp_path, "preferences.json")
    assert p.parent == tmp_path.resolve() or p.parent == tmp_path
    with pytest.raises(ValueError):
        safe_store_path(tmp_path, "../x.json")
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain.preference.propose("..", "x") is None
    assert brain.project.create("a/b", "x") is None


@pytest.mark.unit
def test_26_backup_retention(tmp_path):
    store = BrainV2JsonStore(
        tmp_path / "preferences.json",
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
        max_backups=3,
    )
    for i in range(6):
        store.mutate(lambda doc, i=i: doc["items"].__setitem__(f"k{i}", {"key": f"k{i}", "value": str(i)}))
        time.sleep(0.01)  # distinct mtimes on Windows
    backups = list((tmp_path / "backups").glob("preferences-*.json"))
    assert len(backups) <= 3
    assert DEFAULT_MAX_BACKUPS == 10


@pytest.mark.unit
def test_27_restart_load_durable(tmp_path):
    b1 = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    b1.preference.propose("lang", "ro")
    b1.preference.confirm("lang")
    b1.project.create("p", "P")
    b1.project.set_active("p")
    b2 = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert b2.preference.get("lang").confirmed is True
    assert b2.project.get_active() == "p"


@pytest.mark.unit
def test_28_failure_recovery_no_crash(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    with mock.patch(
        "jarvis.memory.brain_v2.persistence.atomic_write_text",
        side_effect=RuntimeError("boom"),
    ):
        brain.preference.propose("a", "1")
        brain.project.create("p", "P")
    # still callable
    assert create_brain_memory_v2(enabled=True, root_dir=tmp_path) is not None


@pytest.mark.unit
def test_29_flag_on_lazy_create(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert not (tmp_path / "preferences.json").exists()
    brain.preference.propose("k", "v")
    assert (tmp_path / "preferences.json").exists()


@pytest.mark.unit
def test_30_to_34_no_wiring_and_flags_unchanged():
    # Source-level: engine/daemon must not import brain_v2.
    root = Path(__file__).resolve().parents[1]
    engine = (root / "src/jarvis/reply/engine.py").read_text(encoding="utf-8")
    daemon = (root / "src/jarvis/daemon.py").read_text(encoding="utf-8")
    assert "brain_v2" not in engine
    assert "brain_memory_v2" not in engine
    assert "brain_v2" not in daemon
    assert "brain_memory_v2" not in daemon
    # Owner profile / state store / internet learning modules untouched by this slice.
    for rel in (
        "src/jarvis/owner_profile.py",
        "src/jarvis/memory/state_store.py",
        "src/jarvis/memory/learning/internet_learning.py",
        "src/jarvis/memory/learning/internet_research.py",
        "src/jarvis/eval/self_eval.py",
    ):
        # Files exist on clean base; brain_v2 must not be referenced.
        text = (root / rel).read_text(encoding="utf-8")
        assert "brain_v2" not in text
        assert "brain_memory_v2" not in text
    from jarvis.config import get_default_config
    d = get_default_config()
    assert d["brain_memory_v2_enabled"] is False
    # H / owner-triggered development remains default OFF
    assert d["owner_triggered_development_enabled"] is False


@pytest.mark.unit
def test_35_to_37_no_network_shell_git_in_module():
    root = Path(__file__).resolve().parents[1] / "src/jarvis/memory/brain_v2"
    banned = ("socket", "requests", "urllib", "subprocess", "os.system", "git.")
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} contains {token}"


@pytest.mark.unit
def test_38_secret_scan_logs(tmp_path, caplog):
    store = BrainV2JsonStore(
        tmp_path / "preferences.json",
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
    )
    secret = "api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789abcd"
    with caplog.at_level(logging.WARNING, logger="jarvis.memory.brain_v2.persistence"):

        def boom(_doc):
            raise RuntimeError(secret)

        store.mutate(boom)
    joined = " ".join(r.message for r in caplog.records)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789abcd" not in joined
    assert scrub_secrets(secret) != secret or "REDACTED" in joined or "mutate:RuntimeError" in joined


@pytest.mark.unit
def test_39_deterministic_sorted_json(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.preference.propose("b", "2")
    brain.preference.propose("a", "1")
    raw = (tmp_path / "preferences.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert list(data.keys()) == sorted(data.keys())
    # keys inside items dict are sorted by json.dumps(sort_keys=True)
    assert list(data["items"].keys()) == sorted(data["items"].keys())


@pytest.mark.unit
def test_40_windows_paths(tmp_path):
    # Nested Windows-style root still resolves under tmp_path.
    root = tmp_path / "memory" / "brain_v2"
    brain = create_brain_memory_v2(enabled=True, root_dir=root)
    brain.preference.propose("win", "ok")
    assert (root / "preferences.json").is_file()
    # default root helper returns Path (Windows-safe)
    assert isinstance(default_brain_v2_root(), Path)


@pytest.mark.unit
def test_corrupt_bak_skipped_for_valid_timestamped(tmp_path):
    """Recovery must not promote a corrupt .bak when a later backup is valid."""
    primary = tmp_path / "preferences.json"
    bak = tmp_path / "preferences.json.bak"
    backups = tmp_path / "backups"
    backups.mkdir()
    primary.write_text("bad", encoding="utf-8")
    bak.write_text("also-bad", encoding="utf-8")
    good = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "items": {"k": PreferenceMemoryRecord(key="k", value="ok").to_dict()},
    }
    (backups / "preferences-20260102T000000Z.json").write_text(json.dumps(good), encoding="utf-8")
    store = BrainV2JsonStore(
        primary, empty_factory=empty_preferences_document, backups_dir=backups, writable=True
    )
    assert store.snapshot()["items"]["k"]["value"] == "ok"
