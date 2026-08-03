"""Orchestrator feature flag — default OFF."""

from __future__ import annotations

import os

ENV_ENABLED = "CORA_ORCHESTRATOR_ENABLED"


def _truthy(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def orchestrator_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return _truthy(env.get(ENV_ENABLED, ""))
