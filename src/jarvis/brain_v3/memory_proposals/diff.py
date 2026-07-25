"""Structural diff helpers for memory proposals."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _scalar_equal(a: Any, b: Any) -> bool:
    return a == b


def build_diff(
    before: Optional[Mapping[str, Any]],
    after: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Return a structured before/after diff for proposal review.

    Keys present only in ``after`` appear under ``added``.
    Keys removed appear under ``removed``.
    Changed scalar or nested values appear under ``changed``.
    Unchanged keys appear under ``unchanged`` when both sides exist.
    """
    before_dict = dict(before or {})
    after_dict = dict(after or {})

    before_keys: Set[str] = set(before_dict)
    after_keys: Set[str] = set(after_dict)

    added: Dict[str, Any] = {key: after_dict[key] for key in sorted(after_keys - before_keys)}
    removed: Dict[str, Any] = {key: before_dict[key] for key in sorted(before_keys - after_keys)}

    changed: Dict[str, Dict[str, Any]] = {}
    unchanged: Dict[str, Any] = {}

    for key in sorted(before_keys & after_keys):
        old_val = before_dict[key]
        new_val = after_dict[key]
        if _scalar_equal(old_val, new_val):
            unchanged[key] = new_val
        elif _is_mapping(old_val) and _is_mapping(new_val):
            nested = build_diff(old_val, new_val)
            if nested["added"] or nested["removed"] or nested["changed"]:
                changed[key] = {"before": old_val, "after": new_val, "nested": nested}
            else:
                unchanged[key] = new_val
        else:
            changed[key] = {"before": old_val, "after": new_val}

    summary_parts: List[str] = []
    if added:
        summary_parts.append(f"{len(added)} added")
    if removed:
        summary_parts.append(f"{len(removed)} removed")
    if changed:
        summary_parts.append(f"{len(changed)} changed")
    if not summary_parts:
        summary_parts.append("no changes")

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "summary": ", ".join(summary_parts),
        "has_changes": bool(added or removed or changed),
    }
