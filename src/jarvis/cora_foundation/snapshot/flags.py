"""Snapshot feature flag — default ON for bridge export when Core runs; still read-only."""

from __future__ import annotations

import os

ENV_ENABLED = "CORA_SNAPSHOT_ENABLED"


def _truthy(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def snapshot_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    """Default ON so Host can always ask; modules inside remain OFF until enabled."""
    env = environ if environ is not None else os.environ
    raw = env.get(ENV_ENABLED)
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)
