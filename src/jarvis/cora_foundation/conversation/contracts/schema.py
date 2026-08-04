"""Canonical schema identity for conversation contracts v1.

Family is frozen. Incompatible changes require schema_version = 2 (new modules).
Do not edit v1 field semantics after Schema Freeze.
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA_FAMILY = "cora.conversation.contracts"
SCHEMA_VERSION = 1
SCHEMA_ID = f"{SCHEMA_FAMILY}.v{SCHEMA_VERSION}"

KIND_REQUEST = "ConversationRequest"
KIND_CONTEXT = "ConversationContext"
KIND_DECISION = "ConversationDecision"
KIND_RESPONSE = "ConversationResponse"
KIND_STATE = "ConversationState"

ALL_KINDS = frozenset(
    {KIND_REQUEST, KIND_CONTEXT, KIND_DECISION, KIND_RESPONSE, KIND_STATE}
)


def freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Shallow-freeze a mapping for frozen dataclasses."""
    if data is None:
        return MappingProxyType({})
    return MappingProxyType(dict(data))


def envelope(*, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical serialization envelope for Audit / Snapshot / Replay / Debug."""
    if kind not in ALL_KINDS:
        raise ValueError(f"unknown conversation contract kind: {kind}")
    body = dict(payload)
    body.pop("schema_family", None)
    body.pop("schema_version", None)
    body.pop("kind", None)
    return {
        "schema_family": SCHEMA_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        **body,
    }


def dumps_canonical(obj: Mapping[str, Any]) -> str:
    """Stable JSON string (sorted keys) for deterministic tests/replay."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def loads_canonical(raw: str | bytes) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("canonical conversation JSON must be an object")
    return data


def require_v1_envelope(data: Mapping[str, Any]) -> str:
    """Return kind after checking family/version. Raises ValueError on mismatch."""
    family = data.get("schema_family")
    version = data.get("schema_version")
    kind = data.get("kind")
    if family != SCHEMA_FAMILY:
        raise ValueError(f"schema_family must be {SCHEMA_FAMILY!r}, got {family!r}")
    if version != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}, got {version!r}")
    if kind not in ALL_KINDS:
        raise ValueError(f"kind must be one of {sorted(ALL_KINDS)}, got {kind!r}")
    return str(kind)
