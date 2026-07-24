"""TDD: Brain Memory v2 Preference + Project durable vertical slice."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from unittest import mock

import pytest

from jarvis.memory.brain_v2 import create_brain_memory_v2
from jarvis.memory.brain_v2.models import (
    PreferenceMemoryRecord,
    ProjectMemoryRecord,
)
from jarvis.memory.brain_v2.paths import safe_store_path
from jarvis.memory.brain_v2.persistence import BrainV2JsonStore
from jarvis.memory.brain_v2.models import empty_preferences_document
from jarvis.utils.redact import scrub_secrets


@pytest.mark.unit
def test_flag_off_zero_files(tmp_path):
    assert create_brain_memory_v2(enabled=False, root_dir=tmp_path) is None
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.unit
def test_flag_on_no_write_until_mutate(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    assert brain.storage_ok is True
    # Load of missing files must not create them.
    assert not (tmp_path / "preferences.json").exists()
    assert not (tmp_path / "projects.json").exists()


@pytest.mark.unit
def test_preference_round_trip_restart(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    brain.preference.propose("lang", "ro", confidence=0.9, source="owner")
    brain.preference.confirm("lang")

    brain2 = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain2 is not None
    got = brain2.preference.get("lang")
    assert got is not None
    assert got.value == "ro"
    assert got.confirmed is True
    assert got.schema_version == 1


@pytest.mark.unit
def test_project_round_trip_and_active(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    brain.project.create("alpha", "Alpha", summary="first", next_action="plan")
    brain.project.create("beta", "Beta")
    assert brain.project.set_active("beta") is True
    brain.project.update_next_action("beta", "implement slice", last_action="planned")

    brain2 = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain2 is not None
    assert brain2.project.get_active() == "beta"
    beta = brain2.project.get("beta")
    assert beta is not None
    assert beta.next_action == "implement slice"
    assert beta.last_action == "planned"
    assert beta.schema_version == 1


@pytest.mark.unit
def test_propose_does_not_confirm(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    rec = brain.preference.propose("voice", "warm")
    assert rec.confirmed is False
    assert brain.preference.get("voice").confirmed is False


@pytest.mark.unit
def test_reject_delete_archive(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.preference.propose("x", "1")
    assert brain.preference.reject("x") is True
    assert brain.preference.get("x") is None

    brain.preference.propose("y", "2")
    brain.preference.confirm("y")
    assert brain.preference.delete("y") is True
    assert brain.preference.get("y") is None

    brain.project.create("p1", "P1")
    brain.project.set_active("p1")
    assert brain.project.archive("p1") is True
    assert brain.project.get("p1").status == "archived"
    assert brain.project.get_active() is None
    assert brain.project.set_active("p1") is False


@pytest.mark.unit
def test_schema_missing_and_extra_fields():
    raw = {
        "key": "tone",
        "value": "short",
        # missing confidence/source/confirmed/timestamps/schema_version
        "future_field": {"nested": True},
        "also_unknown": 123,
    }
    rec = PreferenceMemoryRecord.from_dict(raw)
    assert rec.key == "tone"
    assert rec.value == "short"
    assert rec.confirmed is False
    assert rec.schema_version == 1
    dumped = rec.to_dict()
    assert "future_field" not in dumped
    assert "also_unknown" not in dumped

    raw_p = {
        "project_id": "demo",
        "name": "Demo",
        "extra_noise": "ignore-me",
    }
    proj = ProjectMemoryRecord.from_dict(raw_p)
    assert proj.status == "active"
    assert "extra_noise" not in proj.to_dict()


@pytest.mark.unit
def test_corrupt_file_recovers_from_bak(tmp_path):
    pref_path = tmp_path / "preferences.json"
    bak = tmp_path / "preferences.json.bak"
    good = {
        "schema_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "items": {
            "k": PreferenceMemoryRecord(key="k", value="v", confirmed=True).to_dict()
        },
    }
    bak.write_text(json.dumps(good), encoding="utf-8")
    pref_path.write_text("{NOT JSON", encoding="utf-8")

    store = BrainV2JsonStore(
        pref_path,
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
    )
    items = store.snapshot()["items"]
    assert items["k"]["value"] == "v"


@pytest.mark.unit
def test_corrupt_all_yields_empty(tmp_path):
    pref_path = tmp_path / "preferences.json"
    pref_path.write_text("!!!", encoding="utf-8")
    (tmp_path / "preferences.json.bak").write_text("!!!", encoding="utf-8")
    store = BrainV2JsonStore(
        pref_path,
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
    )
    assert store.snapshot()["items"] == {}


@pytest.mark.unit
def test_backup_before_overwrite(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.preference.propose("a", "1")
    brain.preference.propose("a", "2")
    backups = list((tmp_path / "backups").glob("preferences-*.json"))
    assert backups, "expected timestamped backup under backups/"
    # Sibling .bak from atomic_write
    assert (tmp_path / "preferences.json.bak").exists()


@pytest.mark.unit
def test_atomic_write_failure_fail_safe(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    with mock.patch(
        "jarvis.memory.brain_v2.persistence.atomic_write_text",
        side_effect=OSError("disk full"),
    ):
        result = brain.preference.propose("z", "nope")
    # mutate returns False → propose returns None; no crash
    assert result is None
    assert brain.preference._store.last_error is not None


@pytest.mark.unit
def test_minimal_concurrency(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            brain.preference.propose(f"k{i}", f"v{i}")
            brain.preference.confirm(f"k{i}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(brain.preference.list()) == 8


@pytest.mark.unit
def test_path_safety(tmp_path):
    with pytest.raises(ValueError):
        safe_store_path(tmp_path, "../escape.json")
    with pytest.raises(ValueError):
        safe_store_path(tmp_path, "secrets.json")
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain.preference.propose("../x", "bad") is None
    assert brain.preference.propose("a/b", "bad") is None
    assert brain.project.create("..", "bad") is None


@pytest.mark.unit
def test_log_redaction(tmp_path, caplog):
    store = BrainV2JsonStore(
        tmp_path / "preferences.json",
        empty_factory=empty_preferences_document,
        backups_dir=tmp_path / "backups",
        writable=True,
    )
    secret = "api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789abcd"
    with caplog.at_level(logging.WARNING, logger="jarvis.memory.brain_v2.persistence"):
        store.last_error = None

        def boom(_doc):
            raise RuntimeError(secret)

        store.mutate(boom)
    joined = " ".join(r.message for r in caplog.records)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789abcd" not in joined
    assert scrub_secrets(secret) in joined or "REDACTED" in joined or "mutate:RuntimeError" in joined


@pytest.mark.unit
def test_deterministic_serialization():
    a = PreferenceMemoryRecord(key="k", value="v", confidence=0.5, source="t", confirmed=False,
                               created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
    b = PreferenceMemoryRecord.from_dict(a.to_dict())
    assert a.to_dict() == b.to_dict()
    text1 = json.dumps(a.to_dict(), sort_keys=True)
    text2 = json.dumps(b.to_dict(), sort_keys=True)
    assert text1 == text2


@pytest.mark.unit
def test_factory_storage_error_fail_safe(tmp_path):
    with mock.patch(
        "jarvis.memory.brain_v2.facade._durable_pref_proj",
        side_effect=RuntimeError("boom"),
    ):
        # Outer try also catches — should still return a facade
        brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert brain is not None
    # Depending on where mock applies: storage_ok False
    assert brain.preference.propose("k", "v") is not None  # memory-only still works


@pytest.mark.unit
def test_update_status(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.project.create("p", "P")
    assert brain.project.update_status("p", "paused").status == "paused"
    assert brain.project.update_status("p", "nope") is None


@pytest.mark.unit
def test_no_pickle_roundtrip_is_json_only(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    brain.preference.propose("k", "v")
    raw = (tmp_path / "preferences.json").read_text(encoding="utf-8")
    assert raw.lstrip().startswith("{")
    json.loads(raw)  # must parse as JSON
