"""Confidence scoring helpers for extraction."""

from __future__ import annotations

from ..conversation.context import SpeakerAttribution


def clamp_confidence(value: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def base_confidence_for_attribution(attribution: SpeakerAttribution) -> float:
    mapping = {
        SpeakerAttribution.USER_DIRECT: 0.75,
        SpeakerAttribution.ASSISTANT_SUGGESTED: 0.45,
        SpeakerAttribution.SYSTEM_OBSERVED: 0.55,
        SpeakerAttribution.QUOTED_UNVERIFIED: 0.25,
    }
    return mapping.get(attribution, 0.35)


def adjust_confidence(
    base: float,
    *,
    negated: bool = False,
    corrected: bool = False,
    quoted: bool = False,
    injection: bool = False,
) -> float:
    score = base
    if corrected:
        score += 0.05
    if negated:
        score += 0.02
    if quoted:
        score -= 0.15
    if injection:
        score -= 0.25
    return clamp_confidence(score)
