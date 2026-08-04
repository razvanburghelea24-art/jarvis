"""Discord LIVE flags — default OFF. Rollback = flag off or Gateway DENY."""

from __future__ import annotations

import os

ENV_LIVE = "CORA_DISCORD_LIVE"
ENV_PHASE = "CORA_DISCORD_LIVE_PHASE"
ENV_TOKEN = "CORA_DISCORD_TOKEN"
ENV_API_BASE = "CORA_DISCORD_API_BASE"

PHASE_READ = 1
PHASE_WRITE = 2
PHASE_MOD = 3

PHASE1_OPS = frozenset({"read_channel", "read_message", "list_channels"})
PHASE2_OPS = PHASE1_OPS | frozenset({"send_message", "edit_message", "delete_message"})
PHASE3_OPS = PHASE2_OPS | frozenset({"timeout_user", "kick_user", "ban_user"})


def discord_live_enabled() -> bool:
    return os.environ.get(ENV_LIVE, "").strip().lower() in {"1", "true", "yes", "on"}


def discord_live_phase() -> int:
    raw = os.environ.get(ENV_PHASE, "1").strip() or "1"
    try:
        phase = int(raw)
    except ValueError:
        return PHASE_READ
    return max(PHASE_READ, min(PHASE_MOD, phase))


def discord_token() -> str:
    return (
        os.environ.get(ENV_TOKEN, "").strip()
        or os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    )


def discord_api_base() -> str:
    return (
        os.environ.get(ENV_API_BASE, "").strip() or "https://discord.com/api/v10"
    ).rstrip("/")


def ops_for_phase(phase: int) -> frozenset[str]:
    if phase >= PHASE_MOD:
        return PHASE3_OPS
    if phase >= PHASE_WRITE:
        return PHASE2_OPS
    return PHASE1_OPS
