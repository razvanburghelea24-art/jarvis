"""Bounded limits for Phase 3 contextual recall."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecallLimits:
    max_items: int = 32
    max_entities: int = 64
    max_relations: int = 64
    max_timeline_events: int = 64
    max_sources: int = 32
    max_characters: int = 12_000
    max_tokens: int = 3_000
    max_graph_depth: int = 2
    max_nodes: int = 128
    max_edges: int = 256
    timeout_ms: int = 250
    min_confidence: float = 0.0
    max_recent_turns: int = 12

    def clamp_results(self, n: int) -> int:
        return max(1, min(int(n), self.max_items))
