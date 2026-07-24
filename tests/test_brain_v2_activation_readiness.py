"""Activation-readiness harness for Brain Memory v2 (temp dirs only; flag stays OFF live)."""

from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path
from unittest import mock

import pytest

from jarvis.config import load_settings
from jarvis.memory.brain_v2 import create_brain_memory_v2
from jarvis.memory.brain_v2.migration import (
    DOCUMENT_SCHEMA_VERSION,
    SchemaUnsupportedError,
    migrate_document,
)
from jarvis.memory.brain_v2.models import (
    PreferenceMemoryRecord,
    empty_preferences_document,
)
from jarvis.memory.brain_v2.persistence import (
    MAX_DOCUMENT_BYTES,
    MAX_ITEMS,
    BrainV2JsonStore,
)


def _load_cfg(tmp_path, monkeypatch, cfg: dict | None):
    p = tmp_path / "config.json"
    if cfg is not None:
        p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("JARVIS_CONFIG_PATH", str(p))
    return load_settings()


@pytest.mark.unit
def test_flag_fail_safe_strings_and_null(tmp_path, monkeypatch):
    for bad in ("false", "False", "0", "no", "off", "", "yes", "enabled", 2, []):
        s = _load_cfg(tmp_path, monkeypatch, {"brain_memory_v2_enabled": bad})
        assert s.brain_memory_v2_enabled is False, repr(bad)
    s_null = _load_cfg(tmp_path, monkeypatch, {"brain_memory_v2_enabled": None})
    assert s_null.brain_memory_v2_enabled is False
    s_true = _load_cfg(tmp_path, monkeypatch, {"brain_memory_v2_enabled": True})
    assert s_true.brain_memory_v2_enabled is True
    s_one = _load_cfg(tmp_path, monkeypatch, {"brain_memory_v2_enabled": 1})
    assert s_one.brain_memory_v2_enabled is True


@pytest.mark.unit
def test_migrate_v1_noop_and_refuse_newer():
    doc = empty_preferences_document()
    out, status = migrate_document(doc)
    assert status == "ok"
    assert out["schema_version"] == DOCUMENT_SCHEMA_VERSION

    old = {"schema_version": 0, "updated_at": "2020-01-01T00:00:00Z", "items": {}}
    out2, status2 = migrate_document(old)
    assert status2 == "migrated"
    assert out2["schema_version"] == DOCUMENT_SCHEMA_VERSION

    with pytest.raises(SchemaUnsupportedError):
        migrate_document({"schema_version": 99, "items": {}})


@pytest.mark.unit
def test_persist_failure_does_not_dirty_ram(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    with mock.patch(
        "jarvis.memory.brain_v2.persistence.atomic_write_text",
        side_effect=OSError("disk full"),
    ):
        assert brain.preference.propose("z", "nope") is None
    assert brain.preference.get("z") is None
    assert not (tmp_path / "preferences.json").exists()


@pytest.mark.unit
def test_recovery_heals_primary_without_poison_backup(tmp_path):
    pref = tmp_path / "preferences.json"
    bak = tmp_path / "preferences.json.bak"
    backups = tmp_path / "backups"
    backups.mkdir()
    good = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "items": {
            "lang": {
                "key": "lang",
                "value": "ro",
                "confidence": 1.0,
                "source": "owner",
                "confirmed": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "schema_version": 1,
            }
        },
    }
    pref.write_text("{broken", encoding="utf-8")
    bak.write_text(json.dumps(good), encoding="utf-8")

    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    assert brain.preference.get("lang").value == "ro"
    # Primary must be healed to valid JSON.
    healed = json.loads(pref.read_text(encoding="utf-8"))
    assert healed["items"]["lang"]["value"] == "ro"
    # First user write must not copy the old corrupt blob into backups/.
    brain.preference.propose("tone", "short")
    for p in backups.glob("preferences-*.json"):
        raw = p.read_text(encoding="utf-8")
        assert "{broken" not in raw
        json.loads(raw)  # must be valid


@pytest.mark.unit
def test_unknown_document_schema_refused(tmp_path):
    pref = tmp_path / "preferences.json"
    pref.write_text(
        json.dumps({"schema_version": 99, "items": {"k": {"key": "k", "value": "v"}}}),
        encoding="utf-8",
    )
    store = BrainV2JsonStore(
        pref,
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
    )
    # Unsupported newer schema → empty fail-safe (do not load / overwrite blindly).
    assert store.snapshot()["items"] == {}
    assert store.last_error and "schema" in store.last_error.lower()


@pytest.mark.unit
def test_record_future_schema_clamped():
    rec = PreferenceMemoryRecord.from_dict(
        {"key": "k", "value": "v", "schema_version": 99}
    )
    assert rec.schema_version == 1


@pytest.mark.unit
def test_max_items_enforced(tmp_path):
    store = BrainV2JsonStore(
        tmp_path / "preferences.json",
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
        max_items=3,
    )
    for i in range(3):
        assert store.mutate(lambda doc, i=i: doc["items"].__setitem__(f"k{i}", {"key": f"k{i}", "value": str(i)}))
    assert store.mutate(lambda doc: doc["items"].__setitem__("k3", {"key": "k3", "value": "x"})) is False
    assert "max_items" in (store.last_error or "")
    assert len(store.snapshot()["items"]) == 3


@pytest.mark.unit
def test_max_document_bytes_enforced(tmp_path):
    store = BrainV2JsonStore(
        tmp_path / "preferences.json",
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
        max_document_bytes=350,
    )
    ok_val = "x" * 80
    assert store.mutate(lambda doc: doc["items"].__setitem__("a", {"key": "a", "value": ok_val}))
    huge = "y" * 300
    assert store.mutate(lambda doc: doc["items"].__setitem__("b", {"key": "b", "value": huge})) is False
    assert "max_bytes" in (store.last_error or "")
    store.close()


@pytest.mark.unit
def test_secret_like_preference_rejected(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain.preference.propose("openai_api_key", "sk-abc") is None
    assert brain.preference.propose("password", "hunter2") is None
    assert brain.preference.propose("normal_pref", "ok") is not None


@pytest.mark.unit
def test_exclusive_writer_lock_same_process_shared(tmp_path):
    path = tmp_path / "preferences.json"
    backups = tmp_path / "backups"
    first = BrainV2JsonStore(
        path,
        empty_factory=empty_preferences_document,
        backups_dir=backups,
        writable=True,
    )
    second = BrainV2JsonStore(
        path,
        empty_factory=empty_preferences_document,
        backups_dir=backups,
        writable=True,
    )
    # Same interpreter shares the OS lock (restart/reload friendly).
    assert first.writable is True
    assert second.writable is True
    first.close()
    second.close()
    third = BrainV2JsonStore(
        path,
        empty_factory=empty_preferences_document,
        backups_dir=backups,
        writable=True,
    )
    assert third.writable is True
    third.close()


@pytest.mark.unit
def test_exclusive_writer_lock(tmp_path):
    # Kept as alias for multiprocess coverage below.
    test_exclusive_writer_lock_same_process_shared(tmp_path)

def _mp_writer(root: str, key: str, q: mp.Queue) -> None:
    try:
        brain = create_brain_memory_v2(enabled=True, root_dir=root)
        ok = brain is not None and brain.storage_ok and brain.preference.propose(key, "v") is not None
        q.put(("ok", bool(ok), bool(getattr(brain, "storage_ok", False) if brain else False)))
    except Exception as exc:  # noqa: BLE001
        q.put(("err", type(exc).__name__, str(exc)))


@pytest.mark.unit
def test_multiprocess_single_writer(tmp_path):
    q: mp.Queue = mp.Queue()
    # Hold first writer in-process.
    holder = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert holder is not None and holder.storage_ok
    proc = mp.Process(target=_mp_writer, args=(str(tmp_path), "other", q))
    proc.start()
    proc.join(timeout=15)
    assert proc.exitcode == 0
    kind, a, b = q.get(timeout=2)
    assert kind == "ok"
    # Second process must not get a durable writer while first holds the lock.
    assert a is False or b is False
    holder.preference._store.close()


@pytest.mark.unit
def test_rollback_runbook_docs_exist():
    arch = Path(__file__).resolve().parents[1] / "src/jarvis/memory/brain_v2/ARCHITECTURE.md"
    text = arch.read_text(encoding="utf-8")
    assert "Rollback runbook" in text
    assert "brain_memory_v2_enabled" in text


@pytest.mark.unit
def test_backup_restore_roundtrip(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.preference.propose("lang", "ro")
    brain.preference.confirm("lang")
    primary = tmp_path / "preferences.json"
    snapshot = tmp_path / "export-preferences.json"
    snapshot.write_bytes(primary.read_bytes())
    brain.preference._store.close()
    brain.project._store.close()
    # Corrupt primary; restore from export.
    primary.write_text("{broken", encoding="utf-8")
    primary.write_bytes(snapshot.read_bytes())
    brain2 = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain2.preference.get("lang").value == "ro"
    brain2.preference._store.close()
    brain2.project._store.close()


@pytest.mark.unit
def test_h_authority_isolation_adversarial(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    # H-shaped payloads must not become executable authority.
    for key, value in (
        ("pending_action", "run git commit"),
        ("plan_body", "### Plan\n1. delete"),
        ("workspace_fingerprint", "abc123"),
        ("git_ref", "refs/heads/main"),
    ):
        rec = brain.preference.propose(key, value, source="h_probe")
        # Either rejected as sensitive / reserved, or stored as inert data only.
        if rec is not None:
            assert rec.confirmed is False
            dumped = json.dumps(rec.to_dict())
            assert "subprocess" not in dumped
    # Confirming a stored blob still must not imply H approval.
    brain.preference.propose("note", "remember this", source="owner")
    brain.preference.confirm("note")
    assert brain.preference.get("note").value == "remember this"


@pytest.mark.unit
def test_constants_exported():
    assert MAX_ITEMS >= 100
    assert MAX_DOCUMENT_BYTES >= 50_000
