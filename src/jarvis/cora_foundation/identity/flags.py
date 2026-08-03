"""Feature flag helpers — Identity default OFF."""

from __future__ import annotations

import os


ENV_ENABLED = "CORA_IDENTITY_ENABLED"


def identity_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    """Return True only when explicitly enabled. Default False (fail-closed)."""
    env = environ if environ is not None else os.environ
    raw = str(env.get(ENV_ENABLED, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}
