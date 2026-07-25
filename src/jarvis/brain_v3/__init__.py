"""Brain V3 — cognitive foundation + Phase 2 conversational memory.

Disabled by default. Zero I/O when factories are called with ``enabled=False``.
Phase 2 is approval-gated and non-executable.
"""

from __future__ import annotations

from .phase2_service import BrainV3Phase2Service, create_brain_v3_phase2
from .service import BrainV3Service, create_brain_v3

__all__ = [
    "BrainV3Service",
    "BrainV3Phase2Service",
    "create_brain_v3",
    "create_brain_v3_phase2",
]
