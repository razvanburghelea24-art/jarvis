"""Contradiction detection among memory candidates."""

from __future__ import annotations

from typing import Iterable, List

from .models import MemoryCandidate
from .normalizer import normalize_candidate_key


def detect_contradictions(candidates: Iterable[MemoryCandidate]) -> List[MemoryCandidate]:
    indexed: dict[tuple[str, str], MemoryCandidate] = {}
    result: List[MemoryCandidate] = []
    for candidate in candidates:
        key = (candidate.candidate_type, normalize_candidate_key(candidate.normalized_value))
        prior = indexed.get(key)
        updated = candidate
        if prior and prior.normalized_value != candidate.normalized_value:
            updated = MemoryCandidate(
                candidate_id=candidate.candidate_id,
                candidate_type=candidate.candidate_type,
                normalized_value=candidate.normalized_value,
                display_value=candidate.display_value,
                source_message_ids=list(candidate.source_message_ids),
                confidence=candidate.confidence,
                reason=f"{candidate.reason}; potential contradiction with prior candidate",
                recommended_action="needs_review",
                source_id=candidate.source_id,
                temporal_scope=candidate.temporal_scope,
                project_scope=candidate.project_scope,
                sensitivity=candidate.sensitivity,
                contradiction_state="potential",
                existing_memory_matches=[prior.candidate_id],
                metadata=dict(candidate.metadata),
            )
        indexed[key] = updated
        result.append(updated)
    return result
