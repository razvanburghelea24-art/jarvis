"""Brain V3 Phase 1 — cognitive foundation (graph, timeline, retrieval, planner).

Disabled by default. Zero I/O when ``enabled=False``. Non-executable plans.
Controlled ingestion defaults to dry-run. No H / shell / network / Git authority.
"""

from __future__ import annotations

from .service import BrainV3Service, create_brain_v3

__all__ = ["BrainV3Service", "create_brain_v3"]
