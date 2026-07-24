"""Facade aggregating the seven Brain Memory v2 modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .episodic import EpisodicMemoryStub
from .ltm import LongTermMemoryStub
from .models import empty_preferences_document, empty_projects_document
from .paths import resolve_brain_v2_root, safe_backups_dir, safe_store_path
from .persistence import BrainV2JsonStore
from .preference import PreferenceMemory
from .project import ProjectMemory
from .semantic import SemanticMemoryStub
from .skill import SkillMemoryStub
from .stm import ShortTermMemoryStub

_PathLike = Union[str, Path]


@dataclass
class BrainMemoryV2:
    """Composition root for Brain Memory v2.

    Construct via :func:`create_brain_memory_v2`. When the feature flag is
    off, callers should not instantiate this at all — the factory returns
    ``None`` so existing behaviour stays byte-identical.
    """

    short_term: ShortTermMemoryStub
    long_term: LongTermMemoryStub
    episodic: EpisodicMemoryStub
    semantic: SemanticMemoryStub
    skill: SkillMemoryStub
    preference: PreferenceMemory
    project: ProjectMemory
    root_dir: Optional[Path] = None
    storage_ok: bool = True

    def clear_all(self) -> None:
        """Reset every module. Test / diagnostic helper only."""
        self.short_term.clear()
        self.long_term.clear()
        self.episodic.clear()
        self.semantic.clear()
        self.skill.clear()
        self.preference.clear()
        self.project.clear()


def _memory_only_pref_proj() -> tuple[PreferenceMemory, ProjectMemory]:
    return (
        PreferenceMemory(
            BrainV2JsonStore(
                path="preferences.json",
                empty_factory=empty_preferences_document,
                writable=False,
            )
        ),
        ProjectMemory(
            BrainV2JsonStore(
                path="projects.json",
                empty_factory=empty_projects_document,
                writable=False,
            )
        ),
    )


def _durable_pref_proj(root: Path) -> tuple[PreferenceMemory, ProjectMemory, bool]:
    """Build durable stores. Returns (pref, proj, ok). Never raises."""
    try:
        backups = safe_backups_dir(root)
        pref_path = safe_store_path(root, "preferences.json")
        proj_path = safe_store_path(root, "projects.json")
        pref_store = BrainV2JsonStore(
            pref_path,
            empty_factory=empty_preferences_document,
            backups_dir=backups,
            writable=True,
        )
        proj_store = BrainV2JsonStore(
            proj_path,
            empty_factory=empty_projects_document,
            backups_dir=backups,
            writable=True,
        )
        pref = PreferenceMemory(pref_store)
        proj = ProjectMemory(proj_store)
        ok = bool(pref_store.writable and proj_store.writable)
        return pref, proj, ok
    except Exception:  # noqa: BLE001 — fail-safe for daemon safety
        pref, proj = _memory_only_pref_proj()
        return pref, proj, False


def create_brain_memory_v2(
    *,
    enabled: bool = False,
    root_dir: Optional[_PathLike] = None,
    persist: bool = True,
) -> Optional[BrainMemoryV2]:
    """Return a facade when ``enabled``, else ``None`` (no side effects / zero I/O).

    Parameters
    ----------
    enabled:
        Feature flag. ``False`` → ``None``, no directories created.
    root_dir:
        Override for ``~/.config/jarvis/memory/brain_v2``. Tests should pass a
        temporary directory.
    persist:
        When ``False``, Preference/Project stay in-process only (still no
        writes). When ``True`` and ``enabled``, durable JSON stores are opened
        (fail-safe: storage errors fall back to memory-only, never crash).
    """
    if not enabled:
        return None

    storage_ok = True
    resolved: Optional[Path] = None
    if persist:
        try:
            resolved = resolve_brain_v2_root(root_dir)
            preference, project, storage_ok = _durable_pref_proj(resolved)
        except Exception:  # noqa: BLE001
            preference, project = _memory_only_pref_proj()
            storage_ok = False
    else:
        preference, project = _memory_only_pref_proj()

    return BrainMemoryV2(
        short_term=ShortTermMemoryStub(),
        long_term=LongTermMemoryStub(),
        episodic=EpisodicMemoryStub(),
        semantic=SemanticMemoryStub(),
        skill=SkillMemoryStub(),
        preference=preference,
        project=project,
        root_dir=resolved,
        storage_ok=storage_ok,
    )
