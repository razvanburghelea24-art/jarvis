"""Confidence category rules for Brain V3 Phase 1."""

from __future__ import annotations

from typing import Any

from .errors import ValidationError
from .limits import BrainV3Limits
from .models import CONFIDENCE_CATEGORIES, clamp_confidence

_NON_VERIFIABLE = frozenset({"inferred", "conflicting", "stale"})

_CATEGORY_RANK = {
    "verified": 6,
    "user_stated": 5,
    "system_observed": 4,
    "imported": 3,
    "inferred": 2,
    "conflicting": 1,
    "stale": 0,
}


def categorize_confidence(category: Any) -> str:
    """Normalise and validate a confidence category string."""
    if category is None:
        raise ValidationError("confidence_category required")
    value = str(category).strip()
    if value not in CONFIDENCE_CATEGORIES:
        raise ValidationError("invalid confidence_category")
    return value


def assert_not_auto_verified(category: str) -> None:
    """Raise when inferred/conflicting/stale would be treated as verified."""
    normalized = categorize_confidence(category)
    if normalized in _NON_VERIFIABLE:
        raise ValidationError(f"{normalized} cannot be verified")


def is_auto_verifiable(category: str) -> bool:
    return categorize_confidence(category) not in _NON_VERIFIABLE


def merge_confidence(
    old: float,
    new: float,
    *,
    limits: BrainV3Limits | None = None,
) -> float:
    """Merge two confidence scores, preferring the higher bounded value."""
    lim = limits or BrainV3Limits()
    old_c = clamp_confidence(old, lim)
    new_c = clamp_confidence(new, lim)
    return clamp_confidence(max(old_c, new_c), lim)


def merge_confidence_category(old: str, new: str) -> str:
    """Merge categories by trust rank; ties prefer the existing category."""
    old_cat = categorize_confidence(old)
    new_cat = categorize_confidence(new)
    if _CATEGORY_RANK.get(new_cat, -1) > _CATEGORY_RANK.get(old_cat, -1):
        return new_cat
    return old_cat
