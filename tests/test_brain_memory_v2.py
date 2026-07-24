"""Interface / stub tests for Brain Memory v2 (no engine wiring)."""

from __future__ import annotations

import pytest

from jarvis.memory.brain_v2 import (
    BrainMemoryV2,
    create_brain_memory_v2,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
)
from jarvis.memory.brain_v2.episodic import EpisodicMemoryStub
from jarvis.memory.brain_v2.ltm import LongTermMemoryStub
from jarvis.memory.brain_v2.preference import PreferenceMemory
from jarvis.memory.brain_v2.project import ProjectMemory
from jarvis.memory.brain_v2.protocols import (
    EpisodicMemory,
    LongTermMemory,
    PreferenceMemory as PreferenceMemoryProtocol,
    ProjectMemory as ProjectMemoryProtocol,
    SemanticMemory,
    ShortTermMemory,
    SkillMemory,
)
from jarvis.memory.brain_v2.semantic import SemanticMemoryStub
from jarvis.memory.brain_v2.skill import SkillMemoryStub
from jarvis.memory.brain_v2.stm import ShortTermMemoryStub


@pytest.mark.unit
def test_factory_disabled_returns_none(tmp_path):
    assert create_brain_memory_v2(enabled=False, root_dir=tmp_path) is None
    assert create_brain_memory_v2() is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_factory_enabled_builds_all_modules(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path)
    assert isinstance(brain, BrainMemoryV2)
    assert isinstance(brain.short_term, ShortTermMemory)
    assert isinstance(brain.long_term, LongTermMemory)
    assert isinstance(brain.episodic, EpisodicMemory)
    assert isinstance(brain.semantic, SemanticMemory)
    assert isinstance(brain.skill, SkillMemory)
    assert isinstance(brain.preference, PreferenceMemoryProtocol)
    assert isinstance(brain.project, ProjectMemoryProtocol)
    assert isinstance(brain.preference, PreferenceMemory)
    assert isinstance(brain.project, ProjectMemory)


@pytest.mark.unit
def test_short_term_append_and_recent():
    stm = ShortTermMemoryStub(max_turns=10)
    a = stm.append_turn("user", "hello", session_id="s1")
    b = stm.append_turn("assistant", "hi", session_id="s1")
    assert a.kind is MemoryKind.SHORT_TERM
    recent = stm.recent(limit=5)
    assert {r.record_id for r in recent} >= {a.record_id, b.record_id}
    assert stm.forget(a.record_id) is True
    assert stm.get(a.record_id) is None


@pytest.mark.unit
def test_long_term_confirm():
    ltm = LongTermMemoryStub()
    rec = ltm.put(
        MemoryRecord(
            kind=MemoryKind.LONG_TERM,
            content="owner lives in Berlin",
            status=MemoryStatus.CANDIDATE,
            confidence=0.4,
            source="test",
        )
    )
    confirmed = ltm.confirm(rec.record_id)
    assert confirmed is not None
    assert confirmed.status is MemoryStatus.ACTIVE


@pytest.mark.unit
def test_episodic_close_episode():
    epi = EpisodicMemoryStub()
    ep = epi.close_episode("sess-9", "Discussed weather and lunch")
    assert ep.session_id == "sess-9"
    assert epi.get(ep.record_id) is not None
    hits = epi.search("weather")
    assert any(h.record_id == ep.record_id for h in hits)


@pytest.mark.unit
def test_semantic_link():
    sem = SemanticMemoryStub()
    a = sem.put(MemoryRecord(kind=MemoryKind.SEMANTIC, content="Berlin", status=MemoryStatus.ACTIVE))
    b = sem.put(MemoryRecord(kind=MemoryKind.SEMANTIC, content="Germany", status=MemoryStatus.ACTIVE))
    sem.link(a.record_id, b.record_id, "located_in")
    assert (a.record_id, b.record_id, "located_in") in sem.links()


@pytest.mark.unit
def test_skill_mark_practiced_does_not_authorise():
    skill = SkillMemoryStub()
    rec = skill.put(
        MemoryRecord(
            kind=MemoryKind.SKILL,
            content="how to summarise a diary day",
            status=MemoryStatus.ACTIVE,
            source="test",
        )
    )
    updated = skill.mark_practiced(rec.record_id)
    assert updated is not None
    assert updated.payload.get("practice_count") == 1
    assert not hasattr(skill, "execute")
    assert not hasattr(skill, "run_skill")


@pytest.mark.unit
def test_preference_propose_vs_confirm():
    pref = PreferenceMemory()  # memory-only
    proposed = pref.propose("tone", "concise", confidence=0.7, source="test")
    assert proposed is not None
    assert proposed.confirmed is False
    assert pref.confirm("tone").confirmed is True


@pytest.mark.unit
def test_project_active_pointer():
    proj = ProjectMemory()
    assert proj.get_active() is None
    assert proj.create("cora-brain-v2", "Brain v2") is not None
    assert proj.set_active("cora-brain-v2") is True
    assert proj.get_active_project() == "cora-brain-v2"
    hits = proj.search("cora-brain-v2")
    assert hits


@pytest.mark.unit
def test_module_rejects_wrong_kind():
    stm = ShortTermMemoryStub()
    with pytest.raises(ValueError):
        stm.put(MemoryRecord(kind=MemoryKind.LONG_TERM, content="nope"))


@pytest.mark.unit
def test_clear_all_isolation(tmp_path):
    brain = create_brain_memory_v2(enabled=True, root_dir=tmp_path, persist=False)
    assert brain is not None
    brain.short_term.append_turn("user", "x")
    brain.long_term.put(MemoryRecord(kind=MemoryKind.LONG_TERM, content="y"))
    brain.clear_all()
    assert brain.short_term.recent() == []
    assert brain.long_term.search("y") == []
