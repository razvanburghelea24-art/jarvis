"""Configurable bounds for Brain V3 Phase 1."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrainV3Limits:
    max_entities: int = 50_000
    max_relations: int = 200_000
    max_timeline_events: int = 100_000
    max_plans: int = 10_000
    max_plan_steps: int = 500
    max_sources: int = 100_000
    max_text_len: int = 8_000
    max_name_len: int = 256
    max_retrieval_results: int = 100
    max_traversal_depth: int = 3
    max_traversal_nodes: int = 500
    max_traversal_edges: int = 2_000
    max_batch_size: int = 1_000
    min_confidence: float = 0.0
    max_confidence: float = 1.0
