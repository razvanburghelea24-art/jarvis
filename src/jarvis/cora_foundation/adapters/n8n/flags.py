"""n8n LIVE flags — default OFF. Workflow strict; READ before EXECUTE."""

from __future__ import annotations

import os

ENV_LIVE = "CORA_N8N_LIVE"
ENV_PHASE = "CORA_N8N_LIVE_PHASE"
ENV_TOKEN = "CORA_N8N_TOKEN"
ENV_API_BASE = "CORA_N8N_API_BASE"

PHASE_READ = 1
PHASE_SOFT_WRITE = 2
PHASE_EXECUTE = 3

PHASE1_OPS = frozenset(
    {
        "workflow_status",
        "list_workflows",
        "execution_status",
        "execution_logs",
        "workflow_info",
    }
)
PHASE2_OPS = PHASE1_OPS | frozenset(
    {"activate_workflow", "deactivate_workflow", "cancel_execution"}
)
PHASE3_OPS = PHASE2_OPS | frozenset({"execute_workflow"})


def n8n_live_enabled() -> bool:
    return os.environ.get(ENV_LIVE, "").strip().lower() in {"1", "true", "yes", "on"}


def n8n_live_phase() -> int:
    raw = os.environ.get(ENV_PHASE, "1").strip() or "1"
    try:
        phase = int(raw)
    except ValueError:
        return PHASE_READ
    return max(PHASE_READ, min(PHASE_EXECUTE, phase))


def n8n_token() -> str:
    return (
        os.environ.get(ENV_TOKEN, "").strip()
        or os.environ.get("N8N_API_KEY", "").strip()
    )


def n8n_api_base() -> str:
    return (
        os.environ.get(ENV_API_BASE, "").strip() or "http://127.0.0.1:5678/api/v1"
    ).rstrip("/")


def ops_for_phase(phase: int) -> frozenset[str]:
    if phase >= PHASE_EXECUTE:
        return PHASE3_OPS
    if phase >= PHASE_SOFT_WRITE:
        return PHASE2_OPS
    return PHASE1_OPS
