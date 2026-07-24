"""Data models for H Phase 1 (plan-only). No I/O, no side effects on import."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

# Internal phase marker — not a live write flag. Never enables execution.
DEVELOPMENT_MODE_PHASE = "plan_only"

# Pinned canonical workspace (Phase 1 refuses anything else).
CANONICAL_WORKSPACE_ROOT = (
    r"C:\Users\Administrator\Downloads\cora-f-real-search-clean"
)
CANONICAL_BRANCH = "feature/cora-f-real-search-clean"

# Explicitly rejected checkouts / trees.
BLOCKED_WORKSPACE_MARKERS = (
    "cora-integration",
    "security-center",
    "SecurityCenter",
    "pr-551",
    "PR-551",
)


class DevelopmentVerdict:
    PLAN_READY = "PLAN_READY"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    BLOCKED_UNSAFE_SCOPE = "BLOCKED_UNSAFE_SCOPE"
    BLOCKED_DIRTY_WORKTREE = "BLOCKED_DIRTY_WORKTREE"
    BLOCKED_WRONG_WORKSPACE = "BLOCKED_WRONG_WORKSPACE"
    STALE_PLAN = "STALE_PLAN"
    PLAN_ONLY_REFUSAL = "PLAN_ONLY_REFUSAL"  # owner asked for direct apply


@dataclass
class PlanCandidateFile:
    path: str
    reason: str
    bytes_read: int = 0


@dataclass
class DevelopmentPlan:
    plan_id: str
    timestamp: str
    objective: str
    component: str
    desired_outcome: str
    constraints: List[str]
    workspace_root: str
    branch: str
    head_sha: str
    working_tree_clean: bool
    state_hash: str
    candidate_files: List[PlanCandidateFile]
    implementation_steps: List[str]
    proposed_tests: List[str]
    risks: List[str]
    security_checks: List[str]
    rollback_strategy: List[str]
    forbidden_files: List[str]
    future_approval_actions: List[str]
    verdict: str
    phase: str = DEVELOPMENT_MODE_PHASE
    applied_changes: bool = False  # always False in Phase 1
    g_consultative_notes: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    ambiguous_or_dangerous: bool = False

    def __post_init__(self) -> None:
        # Invariant: Phase 1 never applies changes, even if a caller passes True.
        object.__setattr__(self, "applied_changes", False)
        object.__setattr__(self, "phase", DEVELOPMENT_MODE_PHASE)

    def to_redacted_audit(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "timestamp": self.timestamp,
            "verdict": self.verdict,
            "objective_len": len(self.objective or ""),
            "component": (self.component or "")[:80],
            "workspace_ok": _roots_equivalent(
                self.workspace_root, CANONICAL_WORKSPACE_ROOT
            ),
            "branch": self.branch,
            "head_sha_prefix": (self.head_sha or "")[:12],
            "working_tree_clean": self.working_tree_clean,
            "n_candidates": len(self.candidate_files),
            "n_steps": len(self.implementation_steps),
            "applied_changes": False,
            "phase": self.phase,
        }


@dataclass
class DevPending:
    """In-memory gate-1 pending. Restart clears it (attribute on dialogue_memory)."""

    objective: str
    component: str
    desired_outcome: str
    constraints: List[str]
    ambiguous_or_dangerous: bool
    created_monotonic: float
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    inspect_allowed: bool = False  # True only after explicit confirm


def new_plan_id() -> str:
    return f"hplan-{uuid.uuid4().hex[:12]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _roots_equivalent(a: str, b: str) -> bool:
    try:
        na = os.path.normcase(os.path.normpath(a or ""))
        nb = os.path.normcase(os.path.normpath(b or ""))
        return na.rstrip("\\/") == nb.rstrip("\\/")
    except Exception:
        return False


def normalize_workspace_root(root: str) -> Tuple[str, Optional[str]]:
    """Return (normalized_root, error_message).

    Blocks path traversal, blocked checkout markers, and symlink/junction
    escapes where ``Path.resolve()`` diverges from the pinned canonical root.
    """
    if not root or not str(root).strip():
        return "", "empty workspace root"
    raw = str(root).strip()
    if "\x00" in raw:
        return raw, "invalid workspace root"
    try:
        norm = os.path.normpath(raw)
    except Exception:
        return raw, "invalid workspace root"
    # Reject explicit parent traversal remaining after norm on relative inputs
    parts = Path(norm).parts
    if ".." in parts:
        return norm, "path traversal in workspace root"
    low = os.path.normcase(norm).lower()
    for marker in BLOCKED_WORKSPACE_MARKERS:
        if marker.lower() in low:
            return norm, f"blocked checkout marker: {marker}"
    canon = os.path.normpath(CANONICAL_WORKSPACE_ROOT)
    canon_key = os.path.normcase(canon).rstrip("\\/")
    norm_key = os.path.normcase(norm).rstrip("\\/")
    # Fast path: exact canonical match (tests / pinned string)
    if norm_key == canon_key:
        return norm, None
    # Resolve both when possible — catches junction/symlink escape to another tree
    try:
        resolved = Path(norm).resolve()
        canon_resolved = Path(canon).resolve()
        if os.path.normcase(str(resolved)).rstrip("\\/") == os.path.normcase(
            str(canon_resolved)
        ).rstrip("\\/"):
            return str(resolved), None
        return norm, "workspace path is not the pinned canonical root (resolved mismatch)"
    except Exception:
        return norm, "workspace path is not the pinned canonical root"
