"""Audit feature flag — default OFF."""

from __future__ import annotations

import os

ENV_ENABLED = "CORA_AUDIT_ENABLED"


def audit_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(ENV_ENABLED, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}
