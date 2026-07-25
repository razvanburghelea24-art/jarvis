"""Speaker attribution for conversational segments."""

from __future__ import annotations

from enum import Enum


class SpeakerAttribution(str, Enum):
    USER_DIRECT = "user_direct"
    ASSISTANT_SUGGESTED = "assistant_suggested"
    SYSTEM_OBSERVED = "system_observed"
    QUOTED_UNVERIFIED = "quoted_unverified"


def attribution_for_role(role: str) -> SpeakerAttribution:
    role = (role or "unknown").lower()
    if role == "user":
        return SpeakerAttribution.USER_DIRECT
    if role == "assistant":
        return SpeakerAttribution.ASSISTANT_SUGGESTED
    if role in {"system", "tool"}:
        return SpeakerAttribution.SYSTEM_OBSERVED
    return SpeakerAttribution.QUOTED_UNVERIFIED
