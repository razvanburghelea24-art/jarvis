"""Build non-executable answer support from a ContextBundle."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .models import AnswerSupport
from ..recall.filters import is_authority_related, redact_for_output
from ..recall.models import ContextBundle


def build_answer_support(
    bundle: ContextBundle,
    *,
    project_snapshot: Optional[Dict[str, Any]] = None,
) -> AnswerSupport:
    facts = []
    prefs = []
    decisions = []
    events = []
    citations = []
    prohibited = []
    uncertainties = list(bundle.unknowns)

    for item in bundle.items:
        text = redact_for_output(f"{item.title}: {item.content}")
        if is_authority_related(text):
            prohibited.append(f"authority_related:{item.item_id}")
            continue
        if item.contradiction_state == "unresolved":
            prohibited.append(f"unresolved_contradiction:{item.title}")
            uncertainties.append(f"contradiction around {item.title}")
            continue
        if item.temporal_state in {"stale", "superseded"}:
            uncertainties.append(f"historical_or_stale:{item.title}")
        if item.item_type == "preference":
            prefs.append(text)
        elif item.item_type == "decision":
            decisions.append(text)
        elif item.item_type == "timeline_event":
            events.append(text)
        else:
            if item.metadata.get("confidence_category") == "inferred":
                uncertainties.append(f"inferred:{item.title}")
            else:
                facts.append(text)
        citations.append(item.item_id)

    for contra in bundle.contradictions:
        if contra.get("needs_review") or contra.get("state") == "unresolved":
            prohibited.append(f"do_not_assert_unresolved:{contra.get('key')}")
            uncertainties.append(f"unresolved:{contra.get('key')}")

    for excl in bundle.excluded_items:
        if str(excl.get("reason", "")).startswith("excluded_sensitivity") or "authority" in str(
            excl.get("reason", "")
        ):
            prohibited.append(f"excluded:{excl.get('item_id')}:{excl.get('reason')}")

    return AnswerSupport(
        supported_facts=facts,
        user_preferences=prefs,
        project_state=dict(project_snapshot or {}),
        relevant_decisions=decisions,
        recent_events=events,
        contradictions=list(bundle.contradictions),
        uncertainties=uncertainties,
        recommended_citations=citations,
        prohibited_claims=prohibited,
    )
