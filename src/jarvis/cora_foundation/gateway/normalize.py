"""Normalize — first immutable pipeline stage."""

from __future__ import annotations

from datetime import datetime, timezone

from .types import CommandEnvelope, NormalizedCommand, SourceChannel


def normalize_command(envelope: CommandEnvelope) -> NormalizedCommand:
    text = " ".join(str(envelope.text or "").strip().split())
    source = envelope.source if isinstance(envelope.source, SourceChannel) else SourceChannel.UNKNOWN
    return NormalizedCommand(
        text=text,
        source=source,
        metadata=dict(envelope.metadata or {}),
        normalized_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
