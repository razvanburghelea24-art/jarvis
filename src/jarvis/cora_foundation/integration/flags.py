"""Integration Hub / adapter feature flags — default OFF."""

from __future__ import annotations

import os

ENV_HUB_ENABLED = "CORA_INTEGRATION_HUB_ENABLED"

_ADAPTER_ENV = {
    "github": "CORA_ADAPTER_GITHUB_ENABLED",
    "railway": "CORA_ADAPTER_RAILWAY_ENABLED",
    "discord": "CORA_ADAPTER_DISCORD_ENABLED",
    "framework": "CORA_ADAPTER_FRAMEWORK_ENABLED",
    "n8n": "CORA_ADAPTER_N8N_ENABLED",
}


def _truthy(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def hub_enabled_from_env(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return _truthy(env.get(ENV_HUB_ENABLED, ""))


def adapter_enabled(name: str, environ: dict[str, str] | None = None) -> bool:
    """Per-adapter gate. Requires hub ON + adapter ON."""
    env = environ if environ is not None else os.environ
    if not hub_enabled_from_env(env):
        return False
    key = _ADAPTER_ENV.get(str(name).lower())
    if not key:
        return False
    return _truthy(env.get(key, ""))
