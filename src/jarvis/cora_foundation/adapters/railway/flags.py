"""Railway LIVE flags — default OFF. Infra strict; READ before WRITE."""

from __future__ import annotations

import os

ENV_LIVE = "CORA_RAILWAY_LIVE"
ENV_PHASE = "CORA_RAILWAY_LIVE_PHASE"
ENV_TOKEN = "CORA_RAILWAY_TOKEN"
ENV_API_BASE = "CORA_RAILWAY_API_BASE"

PHASE_READ = 1
PHASE_SOFT_WRITE = 2
PHASE_HARD_WRITE = 3

PHASE1_OPS = frozenset(
    {
        "project_status",
        "service_status",
        "deployment_status",
        "list_services",
        "list_deployments",
        "logs",
        "environment_info",
    }
)
PHASE2_OPS = PHASE1_OPS | frozenset(
    {"restart_service", "set_variable", "delete_variable"}
)
PHASE3_OPS = PHASE2_OPS | frozenset({"deploy", "rollback"})


def railway_live_enabled() -> bool:
    return os.environ.get(ENV_LIVE, "").strip().lower() in {"1", "true", "yes", "on"}


def railway_live_phase() -> int:
    raw = os.environ.get(ENV_PHASE, "1").strip() or "1"
    try:
        phase = int(raw)
    except ValueError:
        return PHASE_READ
    return max(PHASE_READ, min(PHASE_HARD_WRITE, phase))


def railway_token() -> str:
    return (
        os.environ.get(ENV_TOKEN, "").strip()
        or os.environ.get("RAILWAY_TOKEN", "").strip()
    )


def railway_api_base() -> str:
    return (
        os.environ.get(ENV_API_BASE, "").strip()
        or "https://backboard.railway.app/v1"
    ).rstrip("/")


def ops_for_phase(phase: int) -> frozenset[str]:
    if phase >= PHASE_HARD_WRITE:
        return PHASE3_OPS
    if phase >= PHASE_SOFT_WRITE:
        return PHASE2_OPS
    return PHASE1_OPS
