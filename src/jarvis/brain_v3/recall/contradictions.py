"""Contradiction detection among recall candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import RecallItem
from .temporal import pick_most_recent


def _norm_key(text: str) -> str:
    return " ".join((text or "").lower().split())


def detect_item_contradictions(items: List[RecallItem]) -> Tuple[List[RecallItem], List[Dict[str, Any]]]:
    """Mark conflicting same-key items; prefer most recent verified."""
    by_key: Dict[str, List[RecallItem]] = {}
    for item in items:
        key = _norm_key(item.title) or item.item_id
        by_key.setdefault(key, []).append(item)

    contradictions: List[Dict[str, Any]] = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        contents = {_norm_key(i.content) for i in group}
        if len(contents) <= 1:
            continue
        payload = [
            {
                "item_id": i.item_id,
                "content": i.content[:200],
                "confidence": i.confidence,
                "temporal_state": i.temporal_state,
                "recorded_at": i.metadata.get("recorded_at") or i.metadata.get("updated_at") or i.metadata.get("created_at"),
                "valid_from": i.metadata.get("valid_from"),
                "occurred_at": i.metadata.get("occurred_at"),
            }
            for i in group
        ]
        winner = pick_most_recent(payload)
        winner_id = winner["item_id"] if winner else None
        if winner_id:
            for item in group:
                if item.item_id == winner_id:
                    item.contradiction_state = "historical_transition"
                    item.metadata["supersedes_peers"] = True
                else:
                    item.contradiction_state = "resolved"
                    item.temporal_state = "superseded"
            state = "historical_transition"
        else:
            for item in group:
                item.contradiction_state = "unresolved"
            state = "unresolved"
            winner_id = None
        contradictions.append(
            {
                "key": key,
                "state": state if state != "historical_transition" else "historical_transition",
                "item_ids": [i.item_id for i in group],
                "preferred_item_id": winner_id,
                "needs_review": state == "unresolved",
            }
        )
        if state == "unresolved":
            for item in group:
                item.contradiction_state = "unresolved"
    return items, contradictions
