"""Brain V3 Phase 2: memory proposals and project intelligence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from .conversation import build_conversation
from .errors import ValidationError
from .extraction import extract_candidates
from .memory_proposals import (
    ProposalAuditLog,
    ProposalSet,
    approve,
    build_diff,
    check_expiry,
    commit_proposal,
    generate_approval_token,
    new_proposal,
    new_proposal_set,
    reject,
    rollback_proposal,
)
from .memory_proposals.models import MemoryProposal
from .models import normalize_key
from .project_intelligence import ProjectIntelligenceService, ProjectSnapshot
from .service import BrainV3Service, _resolve_root, create_brain_v3

_PathLike = Union[str, Path]


def _default_phase2_root(root_dir: Optional[_PathLike]) -> Path:
    """Resolve Phase 2 root with the same rules as create_brain_v3."""
    return _resolve_root(root_dir)


def _candidate_to_phase2_dict(cand: Any) -> Dict[str, Any]:
    """Convert extraction MemoryCandidate into proposal-oriented dict."""
    if isinstance(cand, Mapping) and cand.get("kind"):
        return dict(cand)
    base = cand.to_dict() if hasattr(cand, "to_dict") else dict(cand)
    ctype = str(base.get("candidate_type") or "entity")
    display = str(base.get("display_value") or base.get("display_name") or "unnamed")
    if ctype == "event":
        return {
            **base,
            "kind": "timeline_event",
            "event_type": "conversation_note",
            "title": display[:120],
            "description": display[:500],
            "confidence_category": "user_stated",
            "source_reference": "conversation",
        }
    entity_type = ctype if ctype in {
        "person", "project", "component", "decision", "goal", "task",
        "repository", "branch", "commit", "document", "system", "feature",
        "environment", "event", "concept",
    } else "concept"
    if ctype in {"preference", "constraint"}:
        entity_type = "concept"
    return {
        **base,
        "kind": "entity",
        "entity_type": entity_type,
        "canonical_name": normalize_key(str(base.get("normalized_value") or display)),
        "display_name": display[:120],
        "description": display[:500],
        "confidence_category": "user_stated",
        "source_reference": "conversation",
        "attributes": {
            "is_preference": ctype == "preference",
            "sensitivity": base.get("sensitivity", "normal"),
        },
    }


class BrainV3Phase2Service:
    """Phase 2 facade: conversation analysis, proposals, project intelligence."""

    def __init__(
        self,
        *,
        brain_v3: Optional[BrainV3Service] = None,
        root_dir: Optional[_PathLike] = None,
        dry_run: bool = True,
        approval_required: bool = True,
    ) -> None:
        self._brain_v3 = brain_v3
        self._root_dir = _default_phase2_root(root_dir) if root_dir is not None else None
        self.dry_run = dry_run
        self.approval_required = approval_required
        self._audit = ProposalAuditLog(self._root_dir)
        self._project_intel = ProjectIntelligenceService(brain_v3)
        self._proposal_sets: Dict[str, ProposalSet] = {}
        self._proposals: Dict[str, MemoryProposal] = {}
        self.last_error: Optional[str] = None

    @property
    def brain_v3(self) -> Optional[BrainV3Service]:
        return self._brain_v3

    def _note_error(self, exc: BaseException) -> None:
        self.last_error = str(exc)

    def _audit_event(self, event_type: str, data: Mapping[str, Any]) -> None:
        self._audit.append(event_type, data)

    # ── Conversation analysis ─────────────────────────────────────────────

    def analyze_conversation(self, conv: Mapping[str, Any]) -> Dict[str, Any]:
        """Extract structured memory candidates via conversation/ + extraction/."""
        if not isinstance(conv, Mapping):
            raise ValidationError("conversation must be a mapping")

        messages = conv.get("messages") or conv.get("turns") or []
        if not isinstance(messages, list):
            raise ValidationError("messages must be a list")

        raw = {
            "messages": messages,
            "conversation_id": conv.get("id") or conv.get("conversation_id"),
            "title": conv.get("title") or "",
            "source_type": conv.get("source_type") or "conversation",
        }
        candidates = self.extract_memory_candidates(raw)
        result = {
            "conversation_id": conv.get("id") or conv.get("conversation_id"),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "dry_run": self.dry_run,
            "approval_required": self.approval_required,
            "extraction_wired": True,
        }
        self._audit_event("analyze_conversation", {"candidate_count": len(candidates)})
        return result

    def extract_memory_candidates(self, messages: Any) -> List[Dict[str, Any]]:
        """Wire conversation.build_conversation + extraction.extract_candidates."""
        if isinstance(messages, list):
            raw: Dict[str, Any] = {"messages": messages}
        elif isinstance(messages, Mapping):
            raw = dict(messages)
            if "messages" not in raw and "turns" in raw:
                raw = {**raw, "messages": raw["turns"]}
        else:
            raise ValidationError("messages must be a list or conversation mapping")

        # Normalize bare strings / alternate keys for conversation builder.
        normalized_messages: List[Dict[str, Any]] = []
        for index, message in enumerate(raw.get("messages") or []):
            if isinstance(message, Mapping):
                content = str(message.get("content") or message.get("text") or "")
                role = str(message.get("role") or message.get("speaker") or "unknown")
                normalized_messages.append(
                    {
                        "role": role,
                        "content": content,
                        "sequence_index": int(message.get("sequence_index", index)),
                        "message_id": str(message.get("message_id") or ""),
                    }
                )
            else:
                normalized_messages.append(
                    {"role": "unknown", "content": str(message), "sequence_index": index}
                )
        raw["messages"] = normalized_messages
        conversation = build_conversation(raw)
        return [_candidate_to_phase2_dict(c) for c in extract_candidates(conversation)]

    # ── Project intelligence ──────────────────────────────────────────────

    def build_project_snapshot(self, project_name_or_id: str) -> ProjectSnapshot:
        return self._project_intel.build_snapshot(project_name_or_id)

    # ── Memory proposals ────────────────────────────────────────────────────

    def generate_memory_proposals(self, candidates: List[Mapping[str, Any]]) -> ProposalSet:
        """Build a draft ProposalSet from extracted candidates."""
        proposal_set = new_proposal_set(metadata={"dry_run": self.dry_run})
        expires_at = None

        for candidate in candidates:
            kind = str(candidate.get("kind") or "entity")
            if kind == "entity":
                payload = {
                    "entity_type": candidate.get("entity_type", "concept"),
                    "canonical_name": candidate.get("canonical_name") or normalize_key(
                        str(candidate.get("display_name") or "unnamed")
                    ),
                    "display_name": candidate.get("display_name") or "unnamed",
                    "description": candidate.get("description", ""),
                    "confidence_category": candidate.get("confidence_category", "inferred"),
                    "attributes": dict(candidate.get("attributes") or {}),
                }
                before = None
                after = payload
                diff = build_diff(before, after)
                proposal = new_proposal(
                    "entity",
                    payload,
                    before_snapshot=before,
                    after_snapshot=after,
                    diff=diff,
                    expires_at=expires_at,
                    metadata={"source_reference": candidate.get("source_reference")},
                )
            elif kind == "timeline_event":
                payload = {
                    "event_type": candidate.get("event_type", "conversation_note"),
                    "title": candidate.get("title") or "Conversation note",
                    "description": candidate.get("description", ""),
                    "entity_ids": list(candidate.get("entity_ids") or []),
                    "metadata": dict(candidate.get("metadata") or {}),
                }
                diff = build_diff(None, payload)
                proposal = new_proposal(
                    "timeline_event",
                    payload,
                    before_snapshot=None,
                    after_snapshot=payload,
                    diff=diff,
                    expires_at=expires_at,
                    metadata={"source_reference": candidate.get("source_reference")},
                )
            else:
                continue

            if self.approval_required:
                generate_approval_token(proposal)
            proposal_set.add(proposal)
            self._proposals[proposal.id] = proposal

        proposal_set.status = "draft"
        self._proposal_sets[proposal_set.id] = proposal_set
        self._audit_event(
            "generate_memory_proposals",
            {"proposal_set_id": proposal_set.id, "count": len(proposal_set.proposals)},
        )
        return proposal_set

    def approve_proposal(self, proposal: MemoryProposal, *, token: str) -> MemoryProposal:
        try:
            approved = approve(proposal, token=token)
            self._audit_event("approve_proposal", {"proposal_id": proposal.id})
            return approved
        except Exception as exc:
            self._note_error(exc)
            raise

    def reject_proposal(self, proposal: MemoryProposal, *, reason: Optional[str] = None) -> MemoryProposal:
        try:
            rejected = reject(proposal, reason=reason)
            self._audit_event("reject_proposal", {"proposal_id": proposal.id, "reason": reason})
            return rejected
        except Exception as exc:
            self._note_error(exc)
            raise

    def commit_proposal(self, proposal: MemoryProposal) -> MemoryProposal:
        if self.dry_run:
            raise ValidationError("commit forbidden while dry_run=True")
        if self._brain_v3 is None:
            raise ValidationError("brain_v3 service required to commit proposals")
        check_expiry(proposal)
        try:
            committed = commit_proposal(proposal, self._brain_v3)
            self._audit_event("commit_proposal", {"proposal_id": proposal.id, "status": committed.status})
            return committed
        except Exception as exc:
            self._note_error(exc)
            self._audit_event(
                "commit_proposal_failed",
                {"proposal_id": proposal.id, "error": str(exc)},
            )
            raise

    def rollback_proposal(self, proposal: MemoryProposal) -> MemoryProposal:
        if self._brain_v3 is None:
            raise ValidationError("brain_v3 service required to rollback proposals")
        try:
            rolled = rollback_proposal(proposal, self._brain_v3)
            self._audit_event("rollback_proposal", {"proposal_id": proposal.id})
            return rolled
        except Exception as exc:
            self._note_error(exc)
            raise

    # ── Diagnostics ───────────────────────────────────────────────────────

    def get_diagnostics(self) -> Dict[str, Any]:
        brain_diag: Dict[str, Any] = {}
        if self._brain_v3 is not None:
            diag = self._brain_v3.get_diagnostics()
            brain_diag = {
                "enabled": diag.enabled,
                "entity_count": diag.entity_count,
                "relation_count": diag.relation_count,
                "timeline_count": diag.timeline_count,
            }
        return {
            "phase": 2,
            "dry_run": self.dry_run,
            "approval_required": self.approval_required,
            "brain_v3": brain_diag,
            "proposal_sets": len(self._proposal_sets),
            "proposals": len(self._proposals),
            "audit_entries": len(self._audit.entries()),
            "audit_path": str(self._audit.path) if self._audit.path else None,
            "last_error": self.last_error,
        }


def create_brain_v3_phase2(
    *,
    enabled: bool = False,
    root_dir: Optional[_PathLike] = None,
    brain_v3: Optional[BrainV3Service] = None,
    dry_run: bool = True,
    approval_required: bool = True,
) -> Optional[BrainV3Phase2Service]:
    """Return Phase 2 service when enabled; otherwise None with zero I/O."""
    if not enabled:
        return None

    resolved_root = _default_phase2_root(root_dir)
    service_brain_v3 = brain_v3
    if service_brain_v3 is None:
        service_brain_v3 = create_brain_v3(enabled=True, root_dir=resolved_root)

    return BrainV3Phase2Service(
        brain_v3=service_brain_v3,
        root_dir=resolved_root,
        dry_run=dry_run,
        approval_required=approval_required,
    )
