"""Commit approved memory proposals to Brain V3."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, TYPE_CHECKING

from ..errors import ValidationError
from ..models import utc_now_iso
from .approval import approval_valid
from .models import MemoryProposal

if TYPE_CHECKING:
    from ..service import BrainV3Service


class CommitError(ValidationError):
    """Proposal commit or rollback failed."""


def _require_list(payload: Mapping[str, Any], field: str) -> List[Any]:
    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise CommitError(f"{field} must be a list")
    return list(value)


def _rollback_created(service: "BrainV3Service", rollback_data: Dict[str, Any]) -> None:
    """Best-effort rollback of committed artefacts."""
    for entity_id in reversed(rollback_data.get("entity_ids") or []):
        try:
            service.update_entity(entity_id, {"status": "archived"})
        except Exception:
            pass
    for relation_id in reversed(rollback_data.get("relation_ids") or []):
        try:
            service._graph.remove_relation(relation_id)
        except Exception:
            pass


def commit_proposal(proposal: MemoryProposal, brain_v3_service: "BrainV3Service") -> MemoryProposal:
    """Commit an approved proposal when hash matches. Always non-executable."""
    if proposal.execution_forbidden is not True:
        raise CommitError("execution_forbidden must remain true")
    if not approval_valid(proposal):
        raise CommitError("proposal not approved or content hash changed")
    if brain_v3_service.repo.read_only:
        raise CommitError("brain v3 repository is read-only")

    rollback_data: Dict[str, Any] = {
        "entity_ids": [],
        "relation_ids": [],
        "timeline_event_ids": [],
    }
    proposal.rollback_data = rollback_data

    try:
        payload = proposal.payload
        ptype = proposal.proposal_type

        if ptype == "entity":
            entity = brain_v3_service.create_entity(payload)
            rollback_data["entity_ids"].append(entity.id)

        elif ptype == "relation":
            relation = brain_v3_service.create_relation(payload)
            rollback_data["relation_ids"].append(relation.id)

        elif ptype == "timeline_event":
            event = brain_v3_service.record_timeline_event(payload)
            rollback_data["timeline_event_ids"].append(event.id)

        elif ptype == "batch":
            id_map: Dict[str, str] = {}
            for raw_entity in _require_list(payload, "entities"):
                if not isinstance(raw_entity, Mapping):
                    raise CommitError("each entity must be a mapping")
                stored = brain_v3_service.create_entity(raw_entity)
                candidate_id = str(raw_entity.get("id") or stored.id)
                id_map[candidate_id] = stored.id
                rollback_data["entity_ids"].append(stored.id)

            for raw_relation in _require_list(payload, "relations"):
                if not isinstance(raw_relation, Mapping):
                    raise CommitError("each relation must be a mapping")
                relation_data = dict(raw_relation)
                relation_data["source_entity_id"] = id_map.get(
                    relation_data.get("source_entity_id", ""),
                    relation_data.get("source_entity_id"),
                )
                relation_data["target_entity_id"] = id_map.get(
                    relation_data.get("target_entity_id", ""),
                    relation_data.get("target_entity_id"),
                )
                stored = brain_v3_service.create_relation(relation_data)
                rollback_data["relation_ids"].append(stored.id)

            for raw_event in _require_list(payload, "timeline_events"):
                if not isinstance(raw_event, Mapping):
                    raise CommitError("each timeline event must be a mapping")
                event_data = dict(raw_event)
                event_data["entity_ids"] = [
                    id_map.get(eid, eid) for eid in event_data.get("entity_ids") or []
                ]
                stored = brain_v3_service.record_timeline_event(event_data)
                rollback_data["timeline_event_ids"].append(stored.id)
        else:
            raise CommitError(f"unsupported proposal_type: {ptype}")

        proposal.status = "committed"
        proposal.committed_at = utc_now_iso()
        proposal.rollback_data = rollback_data

    except Exception as exc:
        proposal.status = "failed"
        proposal.metadata = {
            **proposal.metadata,
            "commit_error": str(exc),
        }
        try:
            _rollback_created(brain_v3_service, rollback_data)
        except Exception as rollback_exc:
            proposal.metadata["rollback_error"] = str(rollback_exc)
        raise CommitError(f"commit failed: {exc}") from exc

    return proposal


def rollback_proposal(
    proposal: MemoryProposal,
    brain_v3_service: "BrainV3Service",
    *,
    now: Optional[str] = None,
) -> MemoryProposal:
    """Roll back a committed proposal using stored rollback_data."""
    if proposal.status != "committed":
        raise CommitError("only committed proposals can be rolled back")
    if not proposal.rollback_data:
        raise CommitError("rollback_data missing")

    _rollback_created(brain_v3_service, proposal.rollback_data)
    proposal.status = "rolled_back"
    proposal.metadata = {
        **proposal.metadata,
        "rolled_back_at": now or utc_now_iso(),
    }
    return proposal
