"""GitHub LIVE flags — default OFF. Rollback = disable flag or Gateway DENY."""

from __future__ import annotations

import os

ENV_LIVE = "CORA_GITHUB_LIVE"
ENV_PHASE = "CORA_GITHUB_LIVE_PHASE"
ENV_TOKEN = "CORA_GITHUB_TOKEN"
ENV_API_BASE = "CORA_GITHUB_API_BASE"

PHASE_READ = 1
PHASE_WRITE = 2
PHASE_CREATE_PR = 3

PHASE1_OPS = frozenset({"read_repo", "read_pr", "list_branches"})
PHASE2_OPS = PHASE1_OPS | frozenset({"comment_pr", "create_issue", "comment_issue"})
PHASE3_OPS = PHASE2_OPS | frozenset({"create_pr"})


def github_live_enabled() -> bool:
    return os.environ.get(ENV_LIVE, "").strip().lower() in {"1", "true", "yes", "on"}


def github_live_phase() -> int:
    raw = os.environ.get(ENV_PHASE, "1").strip() or "1"
    try:
        phase = int(raw)
    except ValueError:
        return PHASE_READ
    return max(PHASE_READ, min(PHASE_CREATE_PR, phase))


def github_token() -> str:
    return (
        os.environ.get(ENV_TOKEN, "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )


def github_api_base() -> str:
    return (
        os.environ.get(ENV_API_BASE, "").strip()
        or "https://api.github.com"
    ).rstrip("/")


def ops_for_phase(phase: int) -> frozenset[str]:
    if phase >= PHASE_CREATE_PR:
        return PHASE3_OPS
    if phase >= PHASE_WRITE:
        return PHASE2_OPS
    return PHASE1_OPS
