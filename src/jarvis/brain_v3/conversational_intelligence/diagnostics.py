"""Phase 3 diagnostics (read-only, no secrets)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Phase3Diagnostics:
    phase3_enabled: bool = False
    contextual_recall_enabled: bool = False
    read_only: bool = True
    approved_only: bool = True
    include_inferences: bool = False
    recall_requests: int = 0
    selected_items: int = 0
    excluded_items: int = 0
    truncated_requests: int = 0
    timeouts: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    cache_enabled: bool = False
    cache_hits: int = 0
    cache_misses: int = 0
    last_recall_at: Optional[str] = None
    last_error: Optional[str] = None
    _latencies_ms: list[float] = field(default_factory=list, repr=False)

    def record_latency(self, ms: float) -> None:
        self._latencies_ms.append(float(ms))
        if len(self._latencies_ms) > 200:
            self._latencies_ms = self._latencies_ms[-200:]
        vals = sorted(self._latencies_ms)
        if not vals:
            return
        self.average_latency_ms = round(sum(vals) / len(vals), 3)
        idx = min(len(vals) - 1, int(len(vals) * 0.95))
        self.p95_latency_ms = round(vals[idx], 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase3_enabled": self.phase3_enabled,
            "contextual_recall_enabled": self.contextual_recall_enabled,
            "read_only": True,
            "approved_only": self.approved_only,
            "include_inferences": self.include_inferences,
            "recall_requests": self.recall_requests,
            "selected_items": self.selected_items,
            "excluded_items": self.excluded_items,
            "truncated_requests": self.truncated_requests,
            "timeouts": self.timeouts,
            "average_latency_ms": self.average_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "cache_enabled": self.cache_enabled,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "last_recall_at": self.last_recall_at,
            "last_error": self.last_error,
        }
