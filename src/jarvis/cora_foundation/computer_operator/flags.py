"""Computer Operator flags — observe vs control, both default OFF for control."""

from __future__ import annotations

import os

ENV_ENABLED = "CORA_OPERATOR_ENABLED"
ENV_CONTROL_ENABLED = "CORA_OPERATOR_CONTROL_ENABLED"


def _truthy(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def operator_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    """Phase 6A observability gate."""
    env = environ if environ is not None else os.environ
    return _truthy(env.get(ENV_ENABLED, ""))


def operator_control_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    """Phase 6B control gate — requires observe ON + control ON."""
    env = environ if environ is not None else os.environ
    if not operator_enabled_from_env(env):
        return False
    return _truthy(env.get(ENV_CONTROL_ENABLED, ""))
