"""Gateway feature flag — default OFF."""

from __future__ import annotations

import os

ENV_ENABLED = "CORA_GATEWAY_ENABLED"


def gateway_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(ENV_ENABLED, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}
