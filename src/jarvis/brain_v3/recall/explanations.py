"""Explainability helpers for context selection."""

from __future__ import annotations

from typing import Any, Dict, List

from .models import ContextBundle, RecallItem


def explain_item(item: RecallItem) -> Dict[str, Any]:
    return {
        "item_id": item.item_id,
        "reason_for_selection": item.reason_for_selection,
        "rank_score": item.rank_score,
        "rank_breakdown": dict(item.rank_breakdown),
        "approval_state": item.approval_state,
        "temporal_state": item.temporal_state,
        "contradiction_state": item.contradiction_state,
        "confidence": item.confidence,
        "provenance": dict(item.provenance),
        "direct_or_inferred": item.metadata.get("confidence_category", "unknown"),
    }


def explain_bundle(bundle: ContextBundle) -> Dict[str, Any]:
    return {
        "request_id": bundle.request_id,
        "query": bundle.query,
        "selected": [explain_item(i) for i in bundle.items],
        "excluded": list(bundle.excluded_items),
        "contradictions": list(bundle.contradictions),
        "truncated": bundle.truncated,
        "limits_applied": dict(bundle.limits_applied),
        "selection_explanation": bundle.selection_explanation,
        "execution_forbidden": True,
    }


def summarize_selection(items: List[RecallItem], excluded: List[Dict[str, Any]], truncated: bool) -> str:
    parts = [
        f"selected={len(items)}",
        f"excluded={len(excluded)}",
        f"truncated={truncated}",
    ]
    if items:
        top = items[0]
        parts.append(f"top={top.item_id}:{top.reason_for_selection[:80]}")
    return "; ".join(parts)
