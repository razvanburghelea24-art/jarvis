"""Source provenance recording for Brain V3 Phase 1."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from .errors import LimitExceededError, ValidationError
from .limits import BrainV3Limits
from .models import SourceRecord, content_hash, new_id, utc_now_iso
from .validation import build_source_record


class ProvenanceService:
    """Records and retrieves immutable source metadata."""

    def __init__(self, repo: Any, limits: BrainV3Limits | None = None) -> None:
        self._repo = repo
        self._limits = limits or BrainV3Limits()

    def _ensure_writable(self) -> None:
        if getattr(self._repo, "read_only", False):
            raise ValidationError("repository is read-only")

    def record_source(
        self,
        source_type: str,
        source_reference: str,
        *,
        content: str = "",
        content_hash_value: Optional[str] = None,
        trust_level: float = 0.5,
        metadata: Optional[Mapping[str, Any]] = None,
        source_id: Optional[str] = None,
        captured_at: Optional[str] = None,
    ) -> SourceRecord:
        """Persist a new source record with a content hash."""
        self._ensure_writable()
        if self._repo.count_sources() >= self._limits.max_sources:
            raise LimitExceededError("max_sources exceeded")
        digest = content_hash_value or content_hash(content or source_reference)
        record = build_source_record(
            {
                "id": source_id or new_id("src"),
                "source_type": source_type,
                "source_reference": source_reference,
                "content_hash": digest,
                "captured_at": captured_at or utc_now_iso(),
                "trust_level": trust_level,
                "metadata": dict(metadata or {}),
            },
            self._limits,
        )
        return self._repo.create_source(record)

    def get_source(self, source_id: str) -> SourceRecord:
        return self._repo.get_source(source_id)

    def list_sources(self, *, limit: int = 100, offset: int = 0) -> List[SourceRecord]:
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return self._repo.list_sources(limit=bounded, offset=max(0, offset))
