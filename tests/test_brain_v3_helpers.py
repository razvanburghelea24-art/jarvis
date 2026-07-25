"""Shared helpers for Brain V3 Phase 1 tests (tmp_path only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from jarvis.brain_v3 import create_brain_v3
from jarvis.brain_v3.limits import BrainV3Limits
from jarvis.brain_v3.models import ENTITY_TYPES, RELATION_TYPES, new_id, normalize_key
from jarvis.memory.brain_v2 import create_brain_memory_v2


@pytest.fixture
def v3_root(tmp_path: Path) -> Path:
    return tmp_path / "memory" / "brain_v3"


@pytest.fixture
def v2_root(tmp_path: Path) -> Path:
    return tmp_path / "memory" / "brain_v2"


@pytest.fixture
def brain(v3_root: Path):
    svc = create_brain_v3(enabled=True, root_dir=v3_root)
    assert svc is not None
    try:
        yield svc
    finally:
        svc.close()


@pytest.fixture
def brain_v2(v2_root: Path):
    svc = create_brain_memory_v2(enabled=True, root_dir=v2_root, persist=True)
    assert svc is not None
    yield svc


def load_settings_from(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cfg: Optional[dict] = None):
    from jarvis.config import load_settings

    config_path = tmp_path / "config.json"
    if cfg is not None:
        config_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("JARVIS_CONFIG_PATH", str(config_path))
    return load_settings()


def entity_payload(
    *,
    entity_type: str = "person",
    name: str = "alice",
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": new_id("ent"),
        "entity_type": entity_type,
        "canonical_name": name,
        "display_name": name.replace("_", " ").title(),
    }
    payload.update(extra)
    return payload


def relation_payload(
    source_id: str,
    target_id: str,
    *,
    relation_type: str = "related_to",
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": new_id("rel"),
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": relation_type,
    }
    payload.update(extra)
    return payload


def ingest_payload(
    *,
    content: str = "fixture source content",
    entities: Optional[list] = None,
    relations: Optional[list] = None,
    events: Optional[list] = None,
) -> Dict[str, Any]:
    return {
        "source": {
            "source_type": "test",
            "source_reference": content,
            "content": content,
        },
        "entities": entities or [],
        "relations": relations or [],
        "timeline_events": events or [],
    }


def seed_pair(brain, *, left: str = "alpha", right: str = "beta"):
    left_ent = brain.create_entity(entity_payload(name=left))
    right_ent = brain.create_entity(entity_payload(name=right, entity_type="project"))
    rel = brain.create_relation(relation_payload(left_ent.id, right_ent.id))
    return left_ent, right_ent, rel


def tiny_limits(**overrides: int) -> BrainV3Limits:
    defaults = dict(
        max_entities=5,
        max_relations=5,
        max_timeline_events=5,
        max_plans=3,
        max_plan_steps=3,
        max_sources=5,
        max_traversal_depth=2,
        max_traversal_nodes=4,
        max_traversal_edges=4,
        max_retrieval_results=3,
        max_batch_size=10,
    )
    defaults.update(overrides)
    return BrainV3Limits(**defaults)


ALL_ENTITY_TYPES = sorted(ENTITY_TYPES)
ALL_RELATION_TYPES = sorted(RELATION_TYPES)


# ── Phase 2 helpers ───────────────────────────────────────────────────────


@pytest.fixture
def phase2_root(tmp_path: Path) -> Path:
    return tmp_path / "memory" / "brain_v3"


@pytest.fixture
def phase2(phase2_root: Path):
    from jarvis.brain_v3.phase2_service import create_brain_v3_phase2

    svc = create_brain_v3_phase2(enabled=True, root_dir=phase2_root, dry_run=True)
    assert svc is not None
    try:
        yield svc
    finally:
        if svc.brain_v3 is not None:
            svc.brain_v3.close()


@pytest.fixture
def phase2_commit(phase2_root: Path):
    from jarvis.brain_v3.phase2_service import create_brain_v3_phase2

    svc = create_brain_v3_phase2(
        enabled=True, root_dir=phase2_root, dry_run=False, approval_required=True
    )
    assert svc is not None
    try:
        yield svc
    finally:
        if svc.brain_v3 is not None:
            svc.brain_v3.close()


def raw_conversation(*messages: dict, **extra: Any) -> Dict[str, Any]:
    return {"messages": list(messages), **extra}


def conv_msg(role: str, content: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"role": role, "content": content}
    payload.update(extra)
    return payload


def entity_candidate(
    *,
    entity_type: str = "concept",
    name: str = "test entity",
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": "entity",
        "entity_type": entity_type,
        "canonical_name": normalize_key(name),
        "display_name": name,
        "description": f"Candidate for {name}",
        "confidence_category": "user_stated",
        "source_reference": "test",
    }
    payload.update(extra)
    return payload


def timeline_candidate(*, title: str = "Event note", **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": "timeline_event",
        "event_type": "conversation_note",
        "title": title,
        "description": title,
        "source_reference": "test",
    }
    payload.update(extra)
    return payload


def approve_and_get_token(proposal) -> str:
    from jarvis.brain_v3.memory_proposals import generate_approval_token

    return generate_approval_token(proposal)
