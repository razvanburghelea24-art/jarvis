"""Approval workflow for memory proposals."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from ..errors import ValidationError
from ..models import utc_now_iso
from .models import MemoryProposal, proposal_content_hash


class ApprovalError(ValidationError):
    """Proposal approval or rejection failed."""


def _parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _now_iso(now: Optional[str]) -> str:
    return now or utc_now_iso()


def _is_expired(proposal: MemoryProposal, *, now: str) -> bool:
    if not proposal.expires_at:
        return False
    return _parse_iso(now) >= _parse_iso(proposal.expires_at)


def generate_approval_token(proposal: MemoryProposal) -> str:
    """Create a one-time approval token bound to the current content hash."""
    if not proposal.hash_matches():
        raise ApprovalError("proposal content_hash does not match payload")
    token = secrets.token_urlsafe(32)
    proposal.approval_token = f"{proposal.content_hash[:16]}:{token}"
    proposal.approval_token_used = False
    if proposal.status == "draft":
        proposal.status = "awaiting_approval"
    return proposal.approval_token


def check_expiry(proposal: MemoryProposal, *, now: Optional[str] = None) -> bool:
    """Mark proposal expired when past ``expires_at``. Returns True if expired."""
    current = _now_iso(now)
    if proposal.status in {"committed", "rolled_back", "failed", "rejected", "expired"}:
        return proposal.status == "expired"
    if _is_expired(proposal, now=current):
        proposal.status = "expired"
        proposal.approval_token = None
        return True
    return False


def _validate_token(proposal: MemoryProposal, token: str) -> None:
    if not token or not proposal.approval_token:
        raise ApprovalError("approval token required")
    if proposal.approval_token_used:
        raise ApprovalError("approval token already used")
    if token != proposal.approval_token:
        raise ApprovalError("approval token mismatch")
    if not proposal.hash_matches():
        raise ApprovalError("proposal content changed since approval was issued")
    expected_prefix = f"{proposal.content_hash[:16]}:"
    if not proposal.approval_token.startswith(expected_prefix):
        raise ApprovalError("approval token not bound to current content_hash")


def approve(proposal: MemoryProposal, *, token: str, now: Optional[str] = None) -> MemoryProposal:
    """Approve a proposal when token matches content_hash binding (one-time use)."""
    current = _now_iso(now)
    if check_expiry(proposal, now=current):
        raise ApprovalError("proposal expired")
    if proposal.status not in {"awaiting_approval", "draft"}:
        raise ApprovalError(f"cannot approve proposal in status {proposal.status}")
    if not proposal.requires_approval:
        raise ApprovalError("proposal does not require approval")
    if not proposal.hash_matches():
        raise ApprovalError("proposal content_hash does not match payload")

    if proposal.status == "draft" and not proposal.approval_token:
        generate_approval_token(proposal)

    _validate_token(proposal, token)

    proposal.status = "approved"
    proposal.approved_at = current
    proposal.approval_token_used = True
    proposal.approval_token = None
    proposal.metadata = {
        **proposal.metadata,
        "approved_content_hash": proposal.content_hash,
    }
    return proposal


def reject(proposal: MemoryProposal, *, now: Optional[str] = None, reason: Optional[str] = None) -> MemoryProposal:
    """Reject a proposal; clears any pending approval token."""
    current = _now_iso(now)
    if proposal.status in {"committed", "rolled_back", "failed"}:
        raise ApprovalError(f"cannot reject proposal in status {proposal.status}")
    if check_expiry(proposal, now=current) and proposal.status == "expired":
        raise ApprovalError("proposal already expired")

    proposal.status = "rejected"
    proposal.rejected_at = current
    proposal.approval_token = None
    proposal.approval_token_used = False
    if reason:
        proposal.metadata = {**proposal.metadata, "rejection_reason": reason}
    return proposal


def approval_valid(proposal: MemoryProposal) -> bool:
    """Return whether an approved proposal is still valid for commit."""
    if proposal.status != "approved":
        return False
    if not proposal.hash_matches():
        return False
    if proposal.approval_token_used and proposal.approval_token is not None:
        return False
    approved_hash = proposal.metadata.get("approved_content_hash")
    if approved_hash and approved_hash != proposal.content_hash:
        return False
    return proposal_content_hash(proposal.payload) == proposal.content_hash
