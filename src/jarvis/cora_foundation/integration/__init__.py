"""Cora Foundation — Phase 3 Integration Hub (READ-ONLY).

Everything outside Cora Core is an Integration.
Adapters translate only — they do not decide, memorize, policy, or AI.
Default OFF. Per-adapter disable. No live writes.
"""

from .flags import (
    ENV_HUB_ENABLED,
    adapter_enabled,
    hub_enabled_from_env,
)
from .hub import IntegrationHub, get_integration_hub, reset_integration_hub_for_tests
from .types import IntegrationObject, IntegrationSource

__all__ = [
    "ENV_HUB_ENABLED",
    "IntegrationHub",
    "IntegrationObject",
    "IntegrationSource",
    "adapter_enabled",
    "get_integration_hub",
    "hub_enabled_from_env",
    "reset_integration_hub_for_tests",
]
