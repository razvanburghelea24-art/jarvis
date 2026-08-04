"""Framework LIVE flags — default OFF. Game-world strict; READ before WRITE."""

from __future__ import annotations

import os

ENV_LIVE = "CORA_FRAMEWORK_LIVE"
ENV_PHASE = "CORA_FRAMEWORK_LIVE_PHASE"
ENV_TOKEN = "CORA_FRAMEWORK_TOKEN"
ENV_API_BASE = "CORA_FRAMEWORK_API_BASE"

PHASE_READ = 1
PHASE_SOFT_WRITE = 2
PHASE_PLAYER_WRITE = 3

PHASE1_OPS = frozenset(
    {
        "server_status",
        "players",
        "world_time",
        "weather",
        "server_info",
        "health",
        "metrics",
    }
)
PHASE2_OPS = PHASE1_OPS | frozenset({"broadcast", "time_set", "weather_set"})
PHASE3_OPS = PHASE2_OPS | frozenset(
    {"heal", "grow", "teleport", "kick", "ban", "points", "economy"}
)


def framework_live_enabled() -> bool:
    return os.environ.get(ENV_LIVE, "").strip().lower() in {"1", "true", "yes", "on"}


def framework_live_phase() -> int:
    raw = os.environ.get(ENV_PHASE, "1").strip() or "1"
    try:
        phase = int(raw)
    except ValueError:
        return PHASE_READ
    return max(PHASE_READ, min(PHASE_PLAYER_WRITE, phase))


def framework_token() -> str:
    return os.environ.get(ENV_TOKEN, "").strip()


def framework_api_base() -> str:
    return (
        os.environ.get(ENV_API_BASE, "").strip() or "http://127.0.0.1:8787/v1"
    ).rstrip("/")


def ops_for_phase(phase: int) -> frozenset[str]:
    if phase >= PHASE_PLAYER_WRITE:
        return PHASE3_OPS
    if phase >= PHASE_SOFT_WRITE:
        return PHASE2_OPS
    return PHASE1_OPS
