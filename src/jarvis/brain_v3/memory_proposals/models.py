"""Memory proposal data contracts (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import ValidationError
from ..models import content_hash, dumps_json, new_id, utc_now_iso

PROPOSAL_STATUSES = frozenset(
    {
        "draft",
        "awaiting_approval",
        "approved",
        "rejected",
        "expired",
        "committed",
        "rolled_back",
        "failed",
    }
)
PROPOSAL_TYPES = frozenset({"entity", "relation", "timeline_event", "batch"})


def proposal_content_hash(payload: Dict[str, Any]) -> str:
    """Deterministic hash of proposal payload for approval binding."""
    return content_hash(dumps_json(payload))


@dataclass
class MemoryProposal:
    """A single proposed memory mutation awaiting explicit approval."""

    id: str
    proposal_type: str
    payload: Dict[str, Any]
    status: str = "draft"
    content_hash: str = ""
    expires_at: Optional[str] = None
    rollback_data: Optional[Dict[str, Any]] = None
    requires_approval: bool = True
    approval_token: Optional[str] = None
    approval_token_used: bool = False
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    committed_at: Optional[str] = None
    before_snapshot: Optional[Dict[str, Any]] = None
    after_snapshot: Optional[Dict[str, Any]] = None
    diff: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    execution_forbidden: bool = True

    def __post_init__(self) -> None:
        if self.proposal_type not in PROPOSAL_TYPES:
            raise ValidationError(f"invalid proposal_type: {self.proposal_type}")
        if self.status not in PROPOSAL_STATUSES:
            raise ValidationError(f"invalid status: {self.status}")
        if not self.content_hash:
            object.__setattr__(self, "content_hash", proposal_content_hash(self.payload))

    def recompute_hash(self) -> str:
        """Refresh content_hash from current payload."""
        new_hash = proposal_content_hash(self.payload)
        object.__setattr__(self, "content_hash", new_hash)
        return new_hash

    def hash_matches(self) -> bool:
        return self.content_hash == proposal_content_hash(self.payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "proposal_type": self.proposal_type,
            "payload": self.payload,
            "status": self.status,
            "content_hash": self.content_hash,
            "expires_at": self.expires_at,
            "rollback_data": self.rollback_data,
            "requires_approval": True,
            "approval_token": self.approval_token,
            "approval_token_used": self.approval_token_used,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "committed_at": self.committed_at,
            "before_snapshot": self.before_snapshot,
            "after_snapshot": self.after_snapshot,
            "diff": self.diff,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "execution_forbidden": True,
        }


@dataclass
class ProposalSet:
    """Collection of related memory proposals."""

    id: str
    proposals: List[MemoryProposal] = field(default_factory=list)
    status: str = "draft"
    source_reference: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.status not in PROPOSAL_STATUSES:
            raise ValidationError(f"invalid status: {self.status}")

    def add(self, proposal: MemoryProposal) -> None:
        self.proposals.append(proposal)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "proposals": [p.to_dict() for p in self.proposals],
            "status": self.status,
            "source_reference": self.source_reference,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


def new_proposal(
    proposal_type: str,
    payload: Dict[str, Any],
    *,
    proposal_id: Optional[str] = None,
    expires_at: Optional[str] = None,
    before_snapshot: Optional[Dict[str, Any]] = None,
    after_snapshot: Optional[Dict[str, Any]] = None,
    diff: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> MemoryProposal:
    """Factory for a draft memory proposal."""
    return MemoryProposal(
        id=proposal_id or new_id("prop"),
        proposal_type=proposal_type,
        payload=dict(payload),
        status="draft",
        expires_at=expires_at,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        diff=diff,
        metadata=metadata or {},
    )


def new_proposal_set(
    *,
    set_id: Optional[str] = None,
    source_reference: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ProposalSet:
    return ProposalSet(
        id=set_id or new_id("pset"),
        source_reference=source_reference,
        metadata=metadata or {},
    )
