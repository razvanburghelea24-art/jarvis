"""Schema version gates and migrations for Brain Memory v2 JSON documents.

Current supported document schema is version 1. Older stamps are migrated
forward atomically in memory before heal/persist. Newer unknown versions are
refused (never silently reinterpreted).
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .models import DOCUMENT_SCHEMA_VERSION, utc_now_iso

__all__ = [
    "DOCUMENT_SCHEMA_VERSION",
    "SchemaUnsupportedError",
    "migrate_document",
]


class SchemaUnsupportedError(ValueError):
    """Document schema_version is newer than this code understands."""


def _as_version(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def migrate_document(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Normalize a loaded document to the supported schema.

    Returns ``(document, status)`` where status is ``ok`` or ``migrated``.
    Raises :class:`SchemaUnsupportedError` when ``schema_version`` is newer
    than :data:`DOCUMENT_SCHEMA_VERSION`.
    """
    if not isinstance(raw, dict):
        raise TypeError("document must be a dict")
    doc = dict(raw)
    items = doc.get("items")
    if not isinstance(items, dict):
        doc["items"] = {}
    ver = _as_version(doc.get("schema_version", DOCUMENT_SCHEMA_VERSION))
    if ver > DOCUMENT_SCHEMA_VERSION:
        raise SchemaUnsupportedError(
            f"unsupported schema_version={ver} (max={DOCUMENT_SCHEMA_VERSION})"
        )
    if ver < 1:
        # Pre-stamp / corrupt stamp → adopt v1 shape without dropping items.
        doc["schema_version"] = DOCUMENT_SCHEMA_VERSION
        doc.setdefault("updated_at", utc_now_iso())
        return doc, "migrated"
    if ver < DOCUMENT_SCHEMA_VERSION:
        # Reserved for future step-wise upgrades (none yet beyond 1).
        doc["schema_version"] = DOCUMENT_SCHEMA_VERSION
        doc["updated_at"] = utc_now_iso()
        return doc, "migrated"
    doc["schema_version"] = DOCUMENT_SCHEMA_VERSION
    doc.setdefault("updated_at", utc_now_iso())
    return doc, "ok"
