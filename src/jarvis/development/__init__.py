"""Phase 4 · Section H — Owner-Triggered Development (Plan-Only foundation).

Inert unless ``owner_triggered_development_enabled`` is True. Phase 1 never
writes files, never runs shell, never commits, and never activates itself.
"""

from .models import (
    DevelopmentPlan,
    DevelopmentVerdict,
    PlanCandidateFile,
    DEVELOPMENT_MODE_PHASE,
    CANONICAL_WORKSPACE_ROOT,
    CANONICAL_BRANCH,
    normalize_workspace_root,
)
from .owner_development import (
    try_owner_development_command,
    format_development_plan,
    validate_plan_freshness,
    consult_g_on_plan,
    PENDING_TTL_SEC,
)
from .read_only_backend import (
    ReadOnlyRepoBackend,
    FakeReadOnlyBackend,
    AccessDenied,
)
from .live_backend import (
    LiveReadOnlyBackend,
    create_live_backend_after_confirm,
)

__all__ = [
    "DevelopmentPlan",
    "DevelopmentVerdict",
    "PlanCandidateFile",
    "DEVELOPMENT_MODE_PHASE",
    "CANONICAL_WORKSPACE_ROOT",
    "CANONICAL_BRANCH",
    "normalize_workspace_root",
    "try_owner_development_command",
    "format_development_plan",
    "validate_plan_freshness",
    "consult_g_on_plan",
    "PENDING_TTL_SEC",
    "ReadOnlyRepoBackend",
    "FakeReadOnlyBackend",
    "LiveReadOnlyBackend",
    "create_live_backend_after_confirm",
    "AccessDenied",
]
