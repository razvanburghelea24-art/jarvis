"""Labelled project summary sections by confidence category."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

SUMMARY_SECTIONS = (
    "verified",
    "user_stated",
    "assistant_suggested",
    "inferences",
    "unknowns",
)

_CONFIDENCE_TO_SECTION = {
    "verified": "verified",
    "user_stated": "user_stated",
    "system_observed": "verified",
    "imported": "user_stated",
    "inferred": "inferences",
    "conflicting": "unknowns",
    "stale": "unknowns",
}


def _append_unique(section: Dict[str, List[str]], key: str, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    bucket = section.setdefault(key, [])
    if cleaned not in bucket:
        bucket.append(cleaned)


def build_summary(
    *,
    entity: Optional[Mapping[str, Any]] = None,
    related_entities: Optional[List[Mapping[str, Any]]] = None,
    milestones: Optional[List[Mapping[str, Any]]] = None,
    blockers: Optional[List[Mapping[str, Any]]] = None,
    next_steps: Optional[List[Mapping[str, Any]]] = None,
    extra: Optional[Mapping[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    """Build labelled summary sections for a project snapshot."""
    summary: Dict[str, List[str]] = {key: [] for key in SUMMARY_SECTIONS}

    def _classify_item(item: Mapping[str, Any], fallback: str = "inferences") -> str:
        category = str(item.get("confidence_category") or item.get("source") or fallback)
        return _CONFIDENCE_TO_SECTION.get(category, fallback)

    if entity:
        section_key = _classify_item(entity, "user_stated")
        name = str(entity.get("display_name") or entity.get("canonical_name") or "project")
        _append_unique(summary, section_key, f"Project: {name}")
        description = str(entity.get("description") or "")
        if description:
            _append_unique(summary, section_key, description)

    for related in related_entities or []:
        section_key = _classify_item(related, "inferences")
        label = str(related.get("display_name") or related.get("canonical_name") or related.get("id"))
        etype = str(related.get("entity_type") or "entity")
        _append_unique(summary, section_key, f"{etype}: {label}")

    for milestone in milestones or []:
        _append_unique(summary, "verified", f"Milestone: {milestone.get('title', '')}")

    for blocker in blockers or []:
        _append_unique(summary, "unknowns", f"Blocker: {blocker.get('title', '')}")

    for step in next_steps or []:
        source = str(step.get("source") or "assistant_suggested")
        if source in {"assistant_suggested", "inferred"}:
            section = "assistant_suggested" if source == "assistant_suggested" else "inferences"
        elif source == "user_stated":
            section = "user_stated"
        elif source == "verified":
            section = "verified"
        else:
            section = "inferences"
        _append_unique(summary, section, f"Next step: {step.get('title', '')}")

    for key, values in (extra or {}).items():
        if key not in summary:
            continue
        for value in values:
            _append_unique(summary, key, str(value))

    return summary
