"""Brain V3 Phase 1 — comprehensive behavioural pytest suite (tmp_path only)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jarvis.brain_v3 import create_brain_v3
from jarvis.brain_v3.confidence import (
    assert_not_auto_verified,
    categorize_confidence,
    is_auto_verifiable,
    merge_confidence,
    merge_confidence_category,
)
from jarvis.brain_v3.config import SCHEMA_VERSION
from jarvis.brain_v3.diagnostics import diagnostics_for_disabled, gather_diagnostics
from jarvis.brain_v3.errors import (
    BrainV3Error,
    ConflictError,
    LimitExceededError,
    NotFoundError,
    SchemaError,
    ValidationError,
)
from jarvis.brain_v3.limits import BrainV3Limits
from jarvis.brain_v3.migrations import backup_db_file, migrate, verify_schema
from jarvis.brain_v3.models import (
    CONFIDENCE_CATEGORIES,
    ENTITY_TYPES,
    RELATION_TYPES,
    clamp_confidence,
    content_hash,
    normalize_key,
)
from jarvis.brain_v3.repository import BrainV3Repository
from jarvis.brain_v3.validation import (
    build_entity,
    build_relation,
    build_source_record,
    build_timeline_event,
    validate_entity_type,
    validate_relation_type,
)
from jarvis.memory.brain_v2 import create_brain_memory_v2

from tests.test_brain_v3_helpers import (
    ALL_ENTITY_TYPES,
    ALL_RELATION_TYPES,
    entity_payload,
    ingest_payload,
    load_settings_from,
    relation_payload,
    seed_pair,
    tiny_limits,
)

pytest_plugins = ["tests.test_brain_v3_helpers"]
pytestmark = pytest.mark.unit


# ── Factory / zero I/O ────────────────────────────────────────────────────


def test_create_brain_v3_disabled_returns_none(v3_root):
    assert create_brain_v3(enabled=False, root_dir=v3_root) is None
    assert list(v3_root.parent.rglob("*")) == []


def test_create_brain_v3_default_disabled_zero_io(tmp_path):
    assert create_brain_v3() is None
    assert list(tmp_path.iterdir()) == []


def test_create_brain_v3_enabled_creates_db(v3_root):
    svc = create_brain_v3(enabled=True, root_dir=v3_root)
    assert svc is not None
    assert (v3_root / "brain_v3.db").is_file()
    svc.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_create_brain_v3_enabled_flag(v3_root, enabled):
    svc = create_brain_v3(enabled=enabled, root_dir=v3_root)
    if enabled:
        assert svc is not None
        svc.close()
    else:
        assert svc is None


# ── Config strict bool via JARVIS_CONFIG_PATH ─────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("true", False),
        ("yes", False),
        (None, False),
        ([], False),
        ("", False),
        (2, False),
    ],
)
def test_brain_v3_config_strict_bool(tmp_path, monkeypatch, raw, expected):
    settings = load_settings_from(tmp_path, monkeypatch, {"brain_v3_enabled": raw})
    assert settings.brain_v3_enabled is expected


def test_brain_v3_config_defaults_off(tmp_path, monkeypatch):
    settings = load_settings_from(tmp_path, monkeypatch, None)
    assert settings.brain_v3_enabled is False


def test_brain_v3_config_round_trip_enabled(tmp_path, monkeypatch):
    settings = load_settings_from(tmp_path, monkeypatch, {"brain_v3_enabled": True})
    assert settings.brain_v3_enabled is True


# ── Model validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity_type", ALL_ENTITY_TYPES)
def test_validate_entity_type_accepts_known(entity_type):
    assert validate_entity_type(entity_type) == entity_type


@pytest.mark.parametrize("entity_type", ["evil", "", "PERSON", "Person"])
def test_validate_entity_type_rejects_unknown(entity_type):
    with pytest.raises(ValidationError):
        validate_entity_type(entity_type)


@pytest.mark.parametrize("relation_type", ALL_RELATION_TYPES)
def test_validate_relation_type_accepts_known(relation_type):
    assert validate_relation_type(relation_type) == relation_type


@pytest.mark.parametrize("relation_type", ["runs", "exec", ""])
def test_validate_relation_type_rejects_unknown(relation_type):
    with pytest.raises(ValidationError):
        validate_relation_type(relation_type)


@pytest.mark.parametrize("category", sorted(CONFIDENCE_CATEGORIES))
def test_categorize_confidence_accepts_known(category):
    assert categorize_confidence(category) == category


@pytest.mark.parametrize("bad", [None, "made_up", "VERIFIED"])
def test_categorize_confidence_rejects_unknown(bad):
    with pytest.raises(ValidationError):
        categorize_confidence(bad)


def test_build_entity_normalises_canonical_name():
    entity = build_entity(
        {
            "entity_type": "person",
            "canonical_name": "  Alice Smith  ",
            "display_name": "Alice",
        }
    )
    assert entity.canonical_name == "alice smith"


def test_build_relation_rejects_self_loop():
    with pytest.raises(ValidationError):
        build_relation(
            {
                "source_entity_id": "ent_a",
                "target_entity_id": "ent_a",
                "relation_type": "related_to",
            }
        )


def test_build_source_record_requires_fields():
    with pytest.raises(ValidationError):
        build_source_record({"source_type": "test"})


def test_build_timeline_event_requires_title():
    with pytest.raises(ValidationError):
        build_timeline_event({"event_type": "note"})


def test_clamp_confidence_bounds():
    lim = BrainV3Limits(min_confidence=0.2, max_confidence=0.8)
    assert clamp_confidence(0.5, lim) == 0.5
    with pytest.raises(ValidationError):
        clamp_confidence(0.1, lim)
    with pytest.raises(ValidationError):
        clamp_confidence(0.9, lim)


def test_normalize_key_lowercases():
    assert normalize_key("  Foo Bar  ") == "foo bar"


def test_content_hash_stable():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


# ── Schema / migrate ────────────────────────────────────────────────────────


def test_migrate_fresh_db_sets_schema_version(v3_root):
    db_path = v3_root / "brain_v3.db"
    v3_root.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    try:
        version = migrate(conn)
        assert version == SCHEMA_VERSION
        verify_schema(conn)
    finally:
        conn.close()


def test_repository_applies_schema_on_open(v3_root):
    svc = create_brain_v3(enabled=True, root_dir=v3_root)
    assert svc is not None
    diag = svc.get_diagnostics()
    assert diag.schema_version == SCHEMA_VERSION
    assert diag.storage_health == "ok"
    svc.close()


def test_backup_db_file_creates_copy(v3_root):
    svc = create_brain_v3(enabled=True, root_dir=v3_root)
    assert svc is not None
    svc.create_entity(entity_payload(name="backup_me"))
    svc.close()
    db_path = v3_root / "brain_v3.db"
    backup = backup_db_file(db_path)
    assert backup.is_file()
    assert backup.suffix == ".bak"


# ── Entity CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity_type", ALL_ENTITY_TYPES)
def test_create_entity_each_type(brain, entity_type):
    name = f"entity_{entity_type}"
    entity = brain.create_entity(entity_payload(entity_type=entity_type, name=name))
    assert entity.entity_type == entity_type
    assert brain.get_entity(entity.id).canonical_name == normalize_key(name)


def test_update_entity_description(brain):
    entity = brain.create_entity(entity_payload(name="update_me"))
    updated = brain.update_entity(entity.id, {"description": "new details"})
    assert updated.description == "new details"


def test_find_entities_by_query(brain):
    brain.create_entity(entity_payload(name="berlin_resident"))
    brain.create_entity(entity_payload(name="paris_resident"))
    hits = brain.find_entities(query="berlin")
    assert len(hits) == 1
    assert hits[0].canonical_name == normalize_key("berlin_resident")


def test_find_entities_respects_limit(brain):
    for idx in range(5):
        brain.create_entity(entity_payload(name=f"person_{idx}"))
    hits = brain.find_entities(limit=2)
    assert len(hits) == 2


def test_create_duplicate_entity_raises_conflict(brain):
    brain.create_entity(entity_payload(name="duplicate"))
    with pytest.raises(ConflictError):
        brain.create_entity(entity_payload(name="duplicate"))


def test_get_missing_entity_raises(brain):
    with pytest.raises(NotFoundError):
        brain.get_entity("ent_missing")


def test_archive_entity(brain):
    entity = brain.create_entity(entity_payload(name="to_archive"))
    archived = brain._graph.archive_entity(entity.id)
    assert archived.status == "archived"


# ── Relation CRUD ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("relation_type", ALL_RELATION_TYPES)
def test_create_relation_each_type(brain, relation_type):
    left = brain.create_entity(entity_payload(name=f"src_{relation_type}"))
    right = brain.create_entity(entity_payload(name=f"tgt_{relation_type}", entity_type="project"))
    rel = brain.create_relation(relation_payload(left.id, right.id, relation_type=relation_type))
    assert rel.relation_type == relation_type


def test_get_neighbors(brain):
    left, right, rel = seed_pair(brain)
    neighbors = brain.get_neighbors(left.id)
    assert len(neighbors) == 1
    neighbor, edge = neighbors[0]
    assert neighbor.id == right.id
    assert edge.id == rel.id


def test_create_relation_unknown_entity_raises(brain):
    ent = brain.create_entity(entity_payload(name="solo"))
    with pytest.raises(NotFoundError):
        brain.create_relation(relation_payload(ent.id, "ent_missing"))


def test_remove_relation_archives(brain):
    left, right, rel = seed_pair(brain)
    archived = brain.remove_relation(rel.id)
    assert archived.status == "archived"


# ── Graph traverse bounded ──────────────────────────────────────────────────


def test_traverse_respects_depth_limit(v3_root):
    lim = tiny_limits(max_traversal_depth=1, max_traversal_nodes=10, max_traversal_edges=10)
    brain = create_brain_v3(enabled=True, root_dir=v3_root, limits=lim)
    assert brain is not None
    try:
        a = brain.create_entity(entity_payload(name="node_a"))
        b = brain.create_entity(entity_payload(name="node_b", entity_type="project"))
        c = brain.create_entity(entity_payload(name="node_c", entity_type="component"))
        brain.create_relation(relation_payload(a.id, b.id))
        brain.create_relation(relation_payload(b.id, c.id))
        result = brain.traverse(a.id, max_depth=1)
        assert result["depth_limit"] == 1
        assert len(result["nodes"]) <= lim.max_traversal_nodes
    finally:
        brain.close()


def test_traverse_respects_node_limit(v3_root):
    lim = tiny_limits(max_traversal_nodes=2, max_traversal_edges=10, max_traversal_depth=5)
    brain = create_brain_v3(enabled=True, root_dir=v3_root, limits=lim)
    assert brain is not None
    try:
        a = brain.create_entity(entity_payload(name="root"))
        b = brain.create_entity(entity_payload(name="child1", entity_type="project"))
        c = brain.create_entity(entity_payload(name="child2", entity_type="component"))
        brain.create_relation(relation_payload(a.id, b.id))
        brain.create_relation(relation_payload(a.id, c.id))
        result = brain.traverse(a.id)
        assert len(result["nodes"]) <= lim.max_traversal_nodes
    finally:
        brain.close()


def test_find_path_between_entities(brain):
    left, right, _ = seed_pair(brain)
    path = brain._graph.find_path(left.id, right.id)
    assert len(path) == 1


def test_find_path_same_entity_empty(brain):
    ent = brain.create_entity(entity_payload(name="self"))
    assert brain._graph.find_path(ent.id, ent.id) == []


# ── Timeline ────────────────────────────────────────────────────────────────


def test_record_timeline_event(brain):
    ent = brain.create_entity(entity_payload(name="timeline_subject"))
    event = brain.record_timeline_event(
        {
            "event_type": "note",
            "title": "Something happened",
            "entity_ids": [ent.id],
        }
    )
    assert event.title == "Something happened"
    assert ent.id in event.entity_ids


def test_get_timeline_filters_entity(brain):
    ent = brain.create_entity(entity_payload(name="timeline_filter"))
    other = brain.create_entity(entity_payload(name="other", entity_type="project"))
    brain.record_timeline_event(
        {"event_type": "note", "title": "for ent", "entity_ids": [ent.id]}
    )
    brain.record_timeline_event(
        {"event_type": "note", "title": "for other", "entity_ids": [other.id]}
    )
    hits = brain.get_timeline(entity_id=ent.id)
    assert len(hits) == 1
    assert hits[0].title == "for ent"


def test_timeline_dedupe_returns_existing(brain):
    ent = brain.create_entity(entity_payload(name="dedupe"))
    payload = {
        "event_type": "note",
        "title": "duplicate event",
        "occurred_at": "2026-01-01T00:00:00Z",
        "entity_ids": [ent.id],
    }
    first = brain.record_timeline_event(payload)
    second = brain.record_timeline_event(payload)
    assert first.id == second.id


def test_timeline_service_latest_events(brain):
    ent = brain.create_entity(entity_payload(name="latest"))
    brain.record_timeline_event(
        {
            "event_type": "note",
            "title": "older",
            "occurred_at": "2026-01-01T00:00:00Z",
            "entity_ids": [ent.id],
        }
    )
    brain.record_timeline_event(
        {
            "event_type": "note",
            "title": "newer",
            "occurred_at": "2026-02-01T00:00:00Z",
            "entity_ids": [ent.id],
        }
    )
    latest = brain._timeline.latest_events(limit=1)
    assert latest[-1].title == "newer"


# ── Provenance ────────────────────────────────────────────────────────────


def test_provenance_record_source(brain):
    source = brain._provenance.record_source(
        "conversation",
        "user said hello",
        content="user said hello",
        trust_level=0.7,
    )
    assert source.source_type == "conversation"
    fetched = brain._provenance.get_source(source.id)
    assert fetched.content_hash == source.content_hash


def test_provenance_list_sources(brain):
    brain._provenance.record_source("note", "ref-a")
    brain._provenance.record_source("note", "ref-b")
    sources = brain._provenance.list_sources(limit=10)
    assert len(sources) == 2


# ── Confidence: inferred not verified ─────────────────────────────────────


@pytest.mark.parametrize("category", ["inferred", "conflicting", "stale"])
def test_non_verifiable_categories_raise_on_verify(category):
    with pytest.raises(ValidationError):
        assert_not_auto_verified(category)


@pytest.mark.parametrize(
    "category,expected",
    [
        ("verified", True),
        ("user_stated", True),
        ("system_observed", True),
        ("imported", True),
        ("inferred", False),
        ("conflicting", False),
        ("stale", False),
    ],
)
def test_is_auto_verifiable(category, expected):
    assert is_auto_verifiable(category) is expected


def test_update_entity_rejects_inferred_to_verified(brain):
    entity = brain.create_entity(
        entity_payload(name="inferred_one", confidence_category="inferred")
    )
    with pytest.raises(ValidationError):
        brain.update_entity(entity.id, {"confidence_category": "verified"})


def test_merge_confidence_prefers_higher():
    assert merge_confidence(0.3, 0.8) == 0.8


def test_merge_confidence_category_prefers_trust_rank():
    assert merge_confidence_category("inferred", "user_stated") == "user_stated"
    assert merge_confidence_category("user_stated", "inferred") == "user_stated"


# ── Conflicts ───────────────────────────────────────────────────────────────


def test_record_conflict(brain):
    entity = brain.create_entity(entity_payload(name="conflict_subject"))
    conflict = brain._graph.record_conflict(
        entity.id,
        "display_name",
        "Alice",
        "Alicia",
    )
    assert conflict.status == "open"
    assert conflict.requires_confirmation is True


def test_ingest_preview_marks_entity_conflict(brain):
    brain.create_entity(entity_payload(name="existing"))
    preview = brain.ingest_preview(
        ingest_payload(
            entities=[entity_payload(name="existing")],
        )
    )
    assert preview["valid"] is True
    assert preview["entities"][0]["action"] == "conflict"
    assert preview["warnings"]


def test_list_conflicts(brain):
    entity = brain.create_entity(entity_payload(name="conflict_list"))
    brain._graph.record_conflict(entity.id, "description", "a", "b")
    conflicts = brain._graph.list_conflicts(entity_id=entity.id)
    assert len(conflicts) == 1


# ── Retrieval read-only ───────────────────────────────────────────────────


def test_retrieve_context_matches_query(brain):
    brain.create_entity(entity_payload(name="retrieval_target", description="quantum physics"))
    brain.create_entity(entity_payload(name="noise", description="cooking recipes"))
    result = brain.retrieve_context("quantum")
    assert len(result["entities"]) == 1
    assert result["entities"][0].canonical_name == normalize_key("retrieval_target")


def test_retrieve_context_read_only_repo(v3_root):
    writer = create_brain_v3(enabled=True, root_dir=v3_root)
    assert writer is not None
    writer.create_entity(entity_payload(name="readonly_target"))
    writer.close()
    reader = create_brain_v3(enabled=True, root_dir=v3_root, read_only=True)
    assert reader is not None
    try:
        result = reader.retrieve_context("readonly")
        assert len(result["entities"]) == 1
        with pytest.raises(ValidationError):
            reader.create_entity(entity_payload(name="should_fail"))
    finally:
        reader.close()


def test_retrieve_context_respects_min_confidence(brain):
    brain.create_entity(entity_payload(name="low_conf", confidence=0.1))
    brain.create_entity(entity_payload(name="high_conf", confidence=0.9))
    result = brain.retrieve_context("conf", min_confidence=0.5)
    assert len(result["entities"]) == 1
    assert result["entities"][0].canonical_name == normalize_key("high_conf")


def test_retrieve_context_entity_type_filter(brain):
    brain.create_entity(entity_payload(name="person_only", entity_type="person"))
    brain.create_entity(entity_payload(name="project_only", entity_type="project"))
    result = brain.retrieve_context("only", entity_types=["project"])
    assert len(result["entities"]) == 1
    assert result["entities"][0].entity_type == "project"


# ── Planner execution_forbidden ───────────────────────────────────────────


def test_create_plan_steps_non_executable(brain):
    goal = brain.create_entity(entity_payload(name="plan_goal", entity_type="goal"))
    plan = brain.create_plan(
        {
            "title": "Safe plan",
            "goal_entity_id": goal.id,
            "steps": ["Step one", "Step two"],
        }
    )
    assert plan.title == "Safe plan"
    for step in plan.steps:
        assert step.execution_forbidden is True
        assert step.requires_approval is True


def test_get_plan_round_trip(brain):
    plan = brain.create_plan({"title": "Round trip", "steps": ["A"]})
    fetched = brain.get_plan(plan.id)
    assert fetched.id == plan.id
    assert fetched.steps[0].execution_forbidden is True


def test_planner_rejects_empty_title(brain):
    with pytest.raises(ValidationError):
        brain.create_plan({"title": "", "steps": []})


def test_planner_service_mark_step_blocked(brain):
    plan = brain.create_plan({"title": "Block me", "steps": ["Do thing"]})
    step_id = plan.steps[0].id
    blocked = brain._planner.mark_step_blocked(plan.id, step_id, reason="needs review")
    assert blocked.status == "blocked"
    assert blocked.steps[0].execution_forbidden is True


# ── Ingest preview / commit ───────────────────────────────────────────────


def test_ingest_preview_default_dry_run(brain):
    preview = brain.ingest_preview(
        ingest_payload(
            entities=[entity_payload(name="preview_entity")],
        )
    )
    assert preview["dry_run"] is True
    assert preview["committed"] is False
    assert brain.repo.count_entities() == 0


def test_ingest_commit_without_confirm_is_preview(brain):
    result = brain.ingest_commit(
        ingest_payload(entities=[entity_payload(name="no_confirm")]),
        confirm=False,
    )
    assert result["committed"] is False
    assert brain.repo.count_entities() == 0


def test_ingest_commit_with_confirm_writes(brain):
    result = brain.ingest_commit(
        ingest_payload(entities=[entity_payload(name="committed")]),
        confirm=True,
    )
    assert result["committed"] is True
    assert brain.repo.count_entities() == 1
    assert result["created"]["entities"][0]["canonical_name"] == "committed"


def test_ingest_commit_invalid_payload_raises(brain):
    bad = {"source": {"source_type": "x", "source_reference": "y"}, "entities": [{"bad": True}]}
    with pytest.raises(ValidationError):
        brain.ingest_commit(bad, confirm=True)


def test_ingest_preview_requires_source_field(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    try:
        with pytest.raises(ValidationError):
            brain.ingest_preview({"entities": []})
    finally:
        brain.close()


def test_ingest_commit_full_graph(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    try:
        left = entity_payload(name="ing_left")
        right = entity_payload(name="ing_right", entity_type="project")
        payload = ingest_payload(
            entities=[left, right],
            relations=[
                relation_payload(left["id"], right["id"]),
            ],
            events=[
                {
                    "event_type": "note",
                    "title": "ingested event",
                    "entity_ids": [left["id"]],
                }
            ],
        )
        result = brain.ingest_commit(payload, confirm=True)
        assert result["created"]["source"] is not None
        assert len(result["created"]["entities"]) == 2
        assert len(result["created"]["relations"]) == 1
        assert len(result["created"]["timeline_events"]) == 1
    finally:
        brain.close()


# ── Restart persistence ───────────────────────────────────────────────────


def test_restart_persistence_round_trip(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    entity = brain.create_entity(entity_payload(name="persist_me"))
    brain.close()

    brain2 = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain2 is not None
    try:
        loaded = brain2.get_entity(entity.id)
        assert loaded.canonical_name == normalize_key("persist_me")
    finally:
        brain2.close()


def test_restart_persistence_plan_steps(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    plan = brain.create_plan({"title": "persist plan", "steps": ["One", "Two"]})
    brain.close()

    brain2 = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain2 is not None
    try:
        loaded = brain2.get_plan(plan.id)
        assert len(loaded.steps) == 2
        assert all(step.execution_forbidden for step in loaded.steps)
    finally:
        brain2.close()


# ── Corruption / fail-safe ──────────────────────────────────────────────────


def test_truncated_db_reinitialises_schema(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    brain.create_entity(entity_payload(name="before_truncate"))
    brain.close()

    db_path = v3_root / "brain_v3.db"
    db_path.write_bytes(b"")

    brain2 = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain2 is not None
    try:
        assert brain2.repo.count_entities() == 0
        diag = brain2.get_diagnostics()
        assert diag.schema_version == SCHEMA_VERSION
    finally:
        brain2.close()


def test_corrupt_meta_version_fails_read_only(v3_root):
    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    brain.close()

    db_path = v3_root / "brain_v3.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    with pytest.raises(SchemaError):
        BrainV3Repository(db_path, BrainV3Limits(), read_only=True)


# ── Unicode ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "東京",
        "Москва",
        "🌍",
        "naïve",
        "café",
        "مرحبا",
        "Ελλάδα",
        "Ångström",
    ],
)
def test_unicode_entity_names(brain, name):
    entity = brain.create_entity(entity_payload(name=name, display_name=name))
    assert entity.display_name == name
    hits = brain.find_entities(query=name[:2] if len(name) >= 2 else name)
    assert any(h.id == entity.id for h in hits)


@pytest.mark.parametrize(
    "content",
    [
        "用户输入",
        "emoji 🎉 payload",
        "mixed 中文 and English",
    ],
)
def test_unicode_ingest_source(brain, content):
    preview = brain.ingest_preview(ingest_payload(content=content))
    assert preview["source"]["source_reference"] == content


# ── Limits ────────────────────────────────────────────────────────────────


def test_entity_limit_enforced(v3_root):
    lim = tiny_limits(max_entities=2)
    brain = create_brain_v3(enabled=True, root_dir=v3_root, limits=lim)
    assert brain is not None
    try:
        brain.create_entity(entity_payload(name="one"))
        brain.create_entity(entity_payload(name="two"))
        with pytest.raises(LimitExceededError):
            brain.create_entity(entity_payload(name="three"))
    finally:
        brain.close()


def test_plan_step_limit_enforced(v3_root):
    lim = tiny_limits(max_plan_steps=1)
    brain = create_brain_v3(enabled=True, root_dir=v3_root, limits=lim)
    assert brain is not None
    try:
        with pytest.raises(LimitExceededError):
            brain.create_plan({"title": "too many", "steps": ["a", "b"]})
    finally:
        brain.close()


def test_source_limit_enforced(v3_root):
    lim = tiny_limits(max_sources=1)
    brain = create_brain_v3(enabled=True, root_dir=v3_root, limits=lim)
    assert brain is not None
    try:
        brain._provenance.record_source("note", "first")
        with pytest.raises(LimitExceededError):
            brain._provenance.record_source("note", "second")
    finally:
        brain.close()


# ── Diagnostics ───────────────────────────────────────────────────────────


def test_diagnostics_enabled_counts(brain):
    brain.create_entity(entity_payload(name="diag"))
    left, right, _ = seed_pair(brain, left="diag_a", right="diag_b")
    brain.record_timeline_event(
        {"event_type": "note", "title": "diag event", "entity_ids": [left.id]}
    )
    brain.create_plan({"title": "diag plan", "steps": ["s"]})
    diag = brain.get_diagnostics()
    assert diag.enabled is True
    assert diag.entity_count >= 2
    assert diag.relation_count >= 1
    assert diag.timeline_count >= 1
    assert diag.plan_count >= 1
    assert diag.storage_path is not None
    assert "/" not in diag.storage_path or diag.storage_path.count("/") <= 1


def test_diagnostics_disabled():
    diag = diagnostics_for_disabled(last_error="off")
    assert diag.enabled is False
    assert diag.storage_health == "unavailable"


def test_gather_diagnostics_none():
    diag = gather_diagnostics(None)
    assert diag.enabled is False


def test_diagnostics_read_only_flag(v3_root):
    writer = create_brain_v3(enabled=True, root_dir=v3_root)
    assert writer is not None
    writer.close()
    reader = create_brain_v3(enabled=True, root_dir=v3_root, read_only=True)
    assert reader is not None
    try:
        diag = reader.get_diagnostics()
        assert diag.read_only_state is True
        assert diag.storage_health == "degraded"
    finally:
        reader.close()


# ── Brain V2 isolation when V3 reads ──────────────────────────────────────


def test_brain_v2_unchanged_when_v3_reads(v3_root, v2_root, brain_v2):
    brain_v2.preference.propose("tone", "concise")
    brain_v2.preference.confirm("tone")
    brain_v2.project.create("proj-a", "Project A")
    pref_before = json.loads((v2_root / "preferences.json").read_text(encoding="utf-8"))
    proj_before = json.loads((v2_root / "projects.json").read_text(encoding="utf-8"))

    brain = create_brain_v3(enabled=True, root_dir=v3_root)
    assert brain is not None
    try:
        brain.create_entity(entity_payload(name="v3_only"))
        brain.ingest_commit(
            ingest_payload(entities=[entity_payload(name="ingested_v3")]),
            confirm=True,
        )
        brain.retrieve_context("v3")
        brain.get_diagnostics()
    finally:
        brain.close()

    pref_after = json.loads((v2_root / "preferences.json").read_text(encoding="utf-8"))
    proj_after = json.loads((v2_root / "projects.json").read_text(encoding="utf-8"))
    assert pref_after == pref_before
    assert proj_after == proj_before


def test_brain_v2_disabled_zero_io(v2_root):
    assert create_brain_memory_v2(enabled=False, root_dir=v2_root) is None
    assert list(v2_root.rglob("*")) == []


# ── Error tracking ────────────────────────────────────────────────────────


def test_service_records_last_error(brain):
    try:
        brain.create_entity({"entity_type": "bad_type", "canonical_name": "x"})
    except BrainV3Error:
        pass
    assert brain.last_error is not None


def test_read_only_repo_blocks_writes(v3_root):
    writer = create_brain_v3(enabled=True, root_dir=v3_root)
    assert writer is not None
    writer.close()
    brain = create_brain_v3(enabled=True, root_dir=v3_root, read_only=True)
    assert brain is not None
    try:
        with pytest.raises(ValidationError):
            brain.create_entity(entity_payload(name="ro_fail"))
    finally:
        brain.close()


# ── Extra parametrized coverage ───────────────────────────────────────────


@pytest.mark.parametrize("status", ["active", "archived", "superseded", "conflict"])
def test_entity_status_values(brain, status):
    entity = brain.create_entity(
        entity_payload(name=f"status_{status}", status=status)
    )
    assert brain.get_entity(entity.id).status == status


@pytest.mark.parametrize(
    "step_title",
    ["Analyse", "Design", "Review", "Document"],
)
def test_plan_multiple_step_titles(brain, step_title):
    plan = brain.create_plan({"title": "Multi", "steps": [step_title]})
    assert plan.steps[0].title == step_title
    assert plan.steps[0].execution_forbidden is True


@pytest.mark.parametrize(
    "trust",
    [0.0, 0.25, 0.5, 0.75, 1.0],
)
def test_source_trust_levels(brain, trust):
    source = brain._provenance.record_source("note", f"ref-{trust}", trust_level=trust)
    assert source.trust_level == trust


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "updated desc"),
        ("confidence", 0.95),
        ("confidence_category", "user_stated"),
    ],
)
def test_entity_update_fields(brain, field, value):
    entity = brain.create_entity(entity_payload(name=f"upd_{field}"))
    updated = brain.update_entity(entity.id, {field: value})
    assert getattr(updated, field) == value


@pytest.mark.parametrize(
    "query,expected_count",
    [
        ("alpha", 1),
        ("beta", 1),
        ("missing", 0),
    ],
)
def test_find_entities_query_cases(brain, query, expected_count):
    seed_pair(brain)
    hits = brain.find_entities(query=query)
    assert len(hits) == expected_count


@pytest.mark.parametrize(
    "offset,limit,expected_len",
    [
        (0, 1, 1),
        (1, 1, 1),
        (0, 10, 2),
    ],
)
def test_find_entities_pagination(brain, offset, limit, expected_len):
    seed_pair(brain)
    hits = brain.find_entities(limit=limit, offset=offset)
    assert len(hits) == expected_len
