"""Brain V3 schema migration helpers."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import SCHEMA_VERSION
from .errors import SchemaError
from .schema import DDL, REQUIRED_TABLES, SCHEMA_VERSION as DDL_SCHEMA_VERSION

_META_KEY = "schema_version"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def backup_db_file(path: Path) -> Path:
    """Copy ``path`` to ``path.with_suffix('.db.bak')``."""
    backup_path = path.with_suffix(".db.bak")
    if path.exists():
        shutil.copy2(path, backup_path)
    return backup_path


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _read_schema_version(conn: sqlite3.Connection) -> Optional[int]:
    if not _table_exists(conn, "meta"):
        return None
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?",
        (_META_KEY,),
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"invalid {_META_KEY} in meta table") from exc


def _write_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_META_KEY, str(version)),
    )


def _record_migration(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, applied_at)
        VALUES (?, ?)
        """,
        (version, _utc_now_iso()),
    )


def _apply_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    _write_schema_version(conn, DDL_SCHEMA_VERSION)
    _record_migration(conn, DDL_SCHEMA_VERSION)


def verify_schema(conn: sqlite3.Connection) -> None:
    """Raise ``SchemaError`` when required tables are missing."""
    missing = [name for name in REQUIRED_TABLES if not _table_exists(conn, name)]
    if missing:
        raise SchemaError(f"missing tables: {', '.join(missing)}")

    version = _read_schema_version(conn)
    if version is None:
        raise SchemaError("meta.schema_version is missing")
    if version != SCHEMA_VERSION:
        raise SchemaError(
            f"schema version mismatch: db={version}, expected={SCHEMA_VERSION}"
        )


def migrate(conn: sqlite3.Connection) -> int:
    """Ensure the connection is at ``SCHEMA_VERSION``; return applied version."""
    if DDL_SCHEMA_VERSION != SCHEMA_VERSION:
        raise SchemaError("schema module version mismatch with config")

    conn.execute("PRAGMA foreign_keys = ON")
    version = _read_schema_version(conn)

    if version is None:
        _apply_initial_schema(conn)
        conn.commit()
        verify_schema(conn)
        return SCHEMA_VERSION

    if version > SCHEMA_VERSION:
        raise SchemaError(
            f"database schema version {version} is newer than supported {SCHEMA_VERSION}"
        )

    if version == SCHEMA_VERSION:
        verify_schema(conn)
        return version

    # Only v1 exists today; any lower version receives the initial DDL.
    if version < SCHEMA_VERSION:
        _apply_initial_schema(conn)
        conn.commit()
        verify_schema(conn)
        return SCHEMA_VERSION

    verify_schema(conn)
    return version
