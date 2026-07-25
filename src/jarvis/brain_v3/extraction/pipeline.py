"""Rule-based memory candidate extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from ..conversation.context import SpeakerAttribution, attribution_for_role
from ..conversation.models import Conversation, Message
from ..conversation.redaction import redact_secrets
from ..conversation.segmentation import detect_correction, detect_negation, detect_quoted_segments
from ..errors import LimitExceededError
from . import (
    decisions,
    entities,
    events,
    goals,
    preferences,
    projects,
    tasks,
)
from .confidence import adjust_confidence, base_confidence_for_attribution, clamp_confidence
from .contradictions import detect_contradictions
from .models import MemoryCandidate, new_candidate_id
from .normalizer import clamp_candidate_text, normalize_candidate_key


@dataclass(frozen=True)
class ExtractionLimits:
    max_candidates: int = 500
    max_value_length: int = 2_000
    min_confidence: float = 0.0
    max_confidence: float = 1.0


ExtractorFn = Callable[[str], Optional[str]]

_EXTRACTORS: Tuple[Tuple[str, ExtractorFn], ...] = (
    ("preference", preferences.match_preference),
    ("project", projects.match_project),
    ("decision", decisions.match_decision),
    ("goal", goals.match_goal),
    ("task", tasks.match_task),
    ("event", events.match_event),
    ("constraint", entities.match_constraint),
    ("entity", entities.match_entity),
)


def extract_candidates(
    conversation: Conversation,
    *,
    limits: Optional[ExtractionLimits] = None,
) -> List[MemoryCandidate]:
    """Extract heuristic memory candidates from a validated conversation."""
    lim = limits or ExtractionLimits()
    candidates: List[MemoryCandidate] = []

    for message in conversation.messages:
        candidates.extend(
            _extract_from_message(
                message,
                conversation=conversation,
                limits=lim,
            )
        )
        if len(candidates) >= lim.max_candidates:
            raise LimitExceededError("extraction exceeds max candidates")

    candidates = detect_contradictions(candidates)
    return candidates[: lim.max_candidates]


def _extract_from_message(
    message: Message,
    *,
    conversation: Conversation,
    limits: ExtractionLimits,
) -> List[MemoryCandidate]:
    redacted, blocked = redact_secrets(message.content)
    text = redacted
    if not text.strip():
        return []

    attribution = _message_attribution(message, text)
    negated = detect_negation(text)
    corrected = detect_correction(text)
    quoted_segments = detect_quoted_segments(text)
    quoted = bool(quoted_segments) and attribution == SpeakerAttribution.QUOTED_UNVERIFIED

    if blocked:
        return [
            _make_candidate(
                candidate_type="constraint",
                raw_value=text,
                message=message,
                conversation=conversation,
                attribution=attribution,
                reason="secret-like content detected; candidate blocked",
                confidence=0.0,
                recommended_action="ignore",
                sensitivity="blocked",
                limits=limits,
            )
        ]

    results: List[MemoryCandidate] = []
    injection_snippet, is_injection = entities.classify_hostile(text)
    if is_injection and injection_snippet:
        results.append(
            _make_candidate(
                candidate_type="constraint",
                raw_value=injection_snippet,
                message=message,
                conversation=conversation,
                attribution=SpeakerAttribution.QUOTED_UNVERIFIED,
                reason="prompt injection pattern stored as data, not authority",
                confidence=adjust_confidence(
                    0.2,
                    quoted=True,
                    injection=True,
                ),
                recommended_action="ignore",
                limits=limits,
                metadata={"hostile": True},
            )
        )

    for candidate_type, matcher in _EXTRACTORS:
        snippet = matcher(text)
        if not snippet:
            continue
        base = base_confidence_for_attribution(attribution)
        confidence = adjust_confidence(
            base,
            negated=negated,
            corrected=corrected,
            quoted=quoted,
        )
        recommended = _recommended_action(candidate_type, attribution, confidence)
        results.append(
            _make_candidate(
                candidate_type=candidate_type,
                raw_value=snippet,
                message=message,
                conversation=conversation,
                attribution=attribution,
                reason=f"heuristic {candidate_type} match",
                confidence=confidence,
                recommended_action=recommended,
                limits=limits,
            )
        )
    return results


def _message_attribution(message: Message, text: str) -> SpeakerAttribution:
    quoted = detect_quoted_segments(text)
    if quoted and message.role == "user":
        return SpeakerAttribution.QUOTED_UNVERIFIED
    return attribution_for_role(message.role)


def _recommended_action(
    candidate_type: str,
    attribution: SpeakerAttribution,
    confidence: float,
) -> str:
    if attribution == SpeakerAttribution.QUOTED_UNVERIFIED:
        return "needs_review"
    if attribution == SpeakerAttribution.ASSISTANT_SUGGESTED and candidate_type == "preference":
        return "needs_review"
    if confidence < 0.35:
        return "ignore"
    if candidate_type in {"decision", "constraint"}:
        return "create"
    return "create"


def _make_candidate(
    *,
    candidate_type: str,
    raw_value: str,
    message: Message,
    conversation: Conversation,
    attribution: SpeakerAttribution,
    reason: str,
    confidence: float,
    recommended_action: str,
    limits: ExtractionLimits,
    sensitivity: str = "normal",
    metadata: Optional[dict] = None,
) -> MemoryCandidate:
    display = clamp_candidate_text(raw_value, max_len=limits.max_value_length)
    normalized = normalize_candidate_key(display)
    return MemoryCandidate(
        candidate_id=new_candidate_id(),
        candidate_type=candidate_type,
        normalized_value=normalized,
        display_value=display,
        source_message_ids=[message.message_id],
        source_id=conversation.conversation_id,
        confidence=clamp_confidence(confidence, minimum=limits.min_confidence, maximum=limits.max_confidence),
        reason=reason,
        temporal_scope="unspecified",
        project_scope=_infer_project_scope(display),
        sensitivity=sensitivity,
        contradiction_state="none",
        existing_memory_matches=[],
        recommended_action=recommended_action,
        metadata={
            "speaker_attribution": attribution.value,
            **(metadata or {}),
        },
    )


def _infer_project_scope(text: str) -> str:
    lowered = text.lower()
    if "brain v3" in lowered:
        return "brain_v3"
    if "phase" in lowered:
        return "phase"
    if "project" in lowered or "proiect" in lowered:
        return "project"
    return ""
