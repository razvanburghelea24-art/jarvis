"""Deterministic ranking with per-item score breakdown."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .models import RecallItem

_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def score_item(
    item: RecallItem,
    *,
    query: str,
    project_scope: str = "",
    entity_scope: List[str] | None = None,
) -> Tuple[float, Dict[str, float], str]:
    breakdown: Dict[str, float] = {}
    q_tokens = _tokens(query)
    hay = f"{item.title} {item.content}".lower()
    match = 0.0
    if q_tokens:
        hits = sum(1 for t in q_tokens if t in hay)
        match = hits / max(1, len(q_tokens))
        breakdown["query_match"] = round(match * 3.0, 4)
    else:
        breakdown["query_match"] = 0.0

    if project_scope and project_scope.lower() in hay:
        breakdown["same_project"] = 2.0
    else:
        breakdown["same_project"] = 0.0

    scope = set(entity_scope or [])
    if scope and scope.intersection(item.entity_ids):
        breakdown["same_entity"] = 1.5
    else:
        breakdown["same_entity"] = 0.0

    if item.approval_state == "committed":
        breakdown["committed"] = 1.0
    else:
        breakdown["committed"] = 0.0

    cat = str(item.metadata.get("confidence_category") or "")
    if cat in {"verified", "system_observed"}:
        breakdown["high_trust"] = 1.2
    elif cat == "user_stated":
        breakdown["user_approved"] = 1.0
    else:
        breakdown["high_trust"] = 0.0

    breakdown["confidence"] = round(float(item.confidence) * 1.0, 4)

    if item.temporal_state == "current":
        breakdown["temporal_current"] = 1.0
    elif item.temporal_state == "historical":
        breakdown["temporal_historical"] = 0.4
    elif item.temporal_state in {"stale", "superseded"}:
        breakdown["temporal_penalty"] = -1.5
    else:
        breakdown["temporal_neutral"] = 0.0

    if item.contradiction_state == "unresolved":
        breakdown["contradiction_penalty"] = -2.0
    elif item.contradiction_state == "needs_review":
        breakdown["contradiction_penalty"] = -1.0
    else:
        breakdown["contradiction_penalty"] = 0.0

    if cat == "inferred":
        breakdown["inferred_penalty"] = -1.0
    if item.sensitivity != "normal":
        breakdown["sensitivity_penalty"] = -5.0

    total = round(sum(breakdown.values()), 4)
    reasons = [f"{k}={v}" for k, v in breakdown.items() if v]
    reason = "; ".join(reasons) if reasons else "no_positive_signals"
    return total, breakdown, reason


def rank_items(
    items: List[RecallItem],
    *,
    query: str,
    project_scope: str = "",
    entity_scope: List[str] | None = None,
) -> List[RecallItem]:
    scored: List[RecallItem] = []
    for item in items:
        total, breakdown, reason = score_item(
            item,
            query=query,
            project_scope=project_scope,
            entity_scope=entity_scope,
        )
        item.rank_score = total
        item.rank_breakdown = breakdown
        if not item.reason_for_selection:
            item.reason_for_selection = reason
        else:
            item.reason_for_selection = f"{item.reason_for_selection}; {reason}"
        scored.append(item)
    scored.sort(key=lambda i: (-i.rank_score, i.item_id))
    return scored
