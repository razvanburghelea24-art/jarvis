"""Provenance helpers for recall items."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_provenance(
    *,
    source_type: str,
    source_reference: str = "",
    source_id: Optional[str] = None,
    approval_state: str = "committed",
    confidence: float = 0.0,
    confidence_category: str = "",
    temporal_state: str = "unspecified",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "source": source_id or source_reference or source_type,
        "source_type": source_type,
        "source_reference": source_reference,
        "approval_state": approval_state,
        "confidence": confidence,
        "confidence_category": confidence_category,
        "temporal_state": temporal_state,
    }
    if extra:
        payload.update(extra)
    return payload
