"""Read-only diagnostics for Brain V3 Phase 1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .config import SCHEMA_VERSION

_STORAGE_HEALTH_OK = "ok"
_STORAGE_HEALTH_DEGRADED = "degraded"
_STORAGE_HEALTH_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Diagnostics:
    enabled: bool
    schema_version: Optional[int]
    storage_path: Optional[str]
    entity_count: int
    relation_count: int
    timeline_count: int
    plan_count: int
    source_count: int
    last_migration: Optional[str]
    last_error: Optional[str]
    storage_health: str
    read_only_state: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _relative_storage_path(db_path: Path) -> str:
    """Return basename or a short relative segment; never an absolute path."""
    name = db_path.name
    parent = db_path.parent.name
    if parent and parent not in (".", ""):
        return f"{parent}/{name}"
    return name


def _query_last_migration(conn: Any) -> Optional[str]:
    try:
        row = conn.execute(
            """
            SELECT applied_at FROM schema_migrations
            ORDER BY version DESC
            LIMIT 1
            """
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return str(row[0]) if row[0] is not None else None


def _disabled_diagnostics(*, last_error: Optional[str] = None) -> Diagnostics:
    return Diagnostics(
        enabled=False,
        schema_version=None,
        storage_path=None,
        entity_count=0,
        relation_count=0,
        timeline_count=0,
        plan_count=0,
        source_count=0,
        last_migration=None,
        last_error=last_error,
        storage_health=_STORAGE_HEALTH_UNAVAILABLE,
        read_only_state=False,
    )


def gather_diagnostics(service_or_repo: Any = None) -> Diagnostics:
    """Collect safe, non-secret diagnostics from a service or repository."""
    if service_or_repo is None:
        return _disabled_diagnostics()

    repo = service_or_repo
    enabled = True
    last_error: Optional[str] = None

    if hasattr(service_or_repo, "_repo"):
        repo = service_or_repo._repo
        enabled = bool(getattr(service_or_repo, "enabled", True))
        last_error = getattr(service_or_repo, "last_error", None)
    elif hasattr(service_or_repo, "repo"):
        repo = service_or_repo.repo
        enabled = bool(getattr(service_or_repo, "enabled", True))
        last_error = getattr(service_or_repo, "last_error", None)

    if not enabled:
        return _disabled_diagnostics(last_error=last_error)

    db_path = getattr(repo, "db_path", None)
    storage_path: Optional[str] = None
    if db_path is not None:
        storage_path = _relative_storage_path(Path(db_path))

    read_only_state = bool(getattr(repo, "read_only", False))
    storage_health = _STORAGE_HEALTH_OK
    schema_version: Optional[int] = SCHEMA_VERSION
    last_migration: Optional[str] = None
    entity_count = 0
    relation_count = 0
    timeline_count = 0
    plan_count = 0
    source_count = 0

    try:
        entity_count = int(repo.count_entities())
        relation_count = int(repo.count_relations())
        timeline_count = int(repo.count_timeline_events())
        plan_count = int(repo.count_plans())
        source_count = int(repo.count_sources())
        conn = getattr(repo, "conn", None)
        if conn is not None:
            last_migration = _query_last_migration(conn)
    except Exception as exc:  # noqa: BLE001
        storage_health = _STORAGE_HEALTH_DEGRADED
        if last_error is None:
            last_error = str(exc)

    if read_only_state and storage_health == _STORAGE_HEALTH_OK:
        storage_health = _STORAGE_HEALTH_DEGRADED

    return Diagnostics(
        enabled=True,
        schema_version=schema_version,
        storage_path=storage_path,
        entity_count=entity_count,
        relation_count=relation_count,
        timeline_count=timeline_count,
        plan_count=plan_count,
        source_count=source_count,
        last_migration=last_migration,
        last_error=last_error,
        storage_health=storage_health,
        read_only_state=read_only_state,
    )


def diagnostics_for_disabled(*, last_error: Optional[str] = None) -> Diagnostics:
    """Explicit helper when Brain V3 is OFF."""
    return _disabled_diagnostics(last_error=last_error)
