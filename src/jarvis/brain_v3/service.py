"""Brain V3 composition root and controlled ingestion facade."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .diagnostics import Diagnostics, gather_diagnostics
from .errors import BrainV3Error, ValidationError
from .graph import GraphService
from .limits import BrainV3Limits
from .models import Entity, Plan, Relation, SourceRecord, TimelineEvent, content_hash, new_id
from .planner import PlannerService
from .provenance import ProvenanceService
from .repository import BrainV3Repository
from .retrieval import retrieve_context as _retrieve_context
from .timeline import TimelineService
from .validation import (
    build_entity,
    build_relation,
    build_source_record,
    build_timeline_event,
)

_PathLike = Union[str, Path]
_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _default_config_dir() -> Path:
    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().resolve().parent
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve() / "jarvis"
    return Path.home() / ".config" / "jarvis"


def _default_brain_v3_root() -> Path:
    return _default_config_dir() / "memory" / "brain_v3"


def _resolve_root(root_dir: Optional[_PathLike]) -> Path:
    if root_dir is None:
        return _default_brain_v3_root()
    return Path(root_dir).expanduser().resolve()


def _tokenize(query: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(query or "")]


def _entity_matches(entity: Entity, tokens: List[str]) -> bool:
    if not tokens:
        return True
    haystacks = [
        entity.display_name.lower(),
        entity.canonical_name.lower(),
        entity.description.lower(),
        " ".join(alias.lower() for alias in entity.aliases),
    ]
    joined = " ".join(haystacks)
    return any(token in joined for token in tokens)


def _require_dict(payload: Mapping[str, Any], field: str) -> Dict[str, Any]:
    value = payload.get(field)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a dict")
    return dict(value)


def _require_list(payload: Mapping[str, Any], field: str) -> List[Any]:
    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    return list(value)


class BrainV3Service:
    """Stable internal API wrapping graph, timeline, provenance, and planner services."""

    def __init__(
        self,
        repo: BrainV3Repository,
        *,
        enabled: bool = True,
        limits: BrainV3Limits | None = None,
    ) -> None:
        self._limits = limits or repo.limits
        self._repo = repo
        self.enabled = enabled
        self.last_error: Optional[str] = None
        self._graph = GraphService(repo, self._limits)
        self._timeline = TimelineService(repo, self._limits)
        self._provenance = ProvenanceService(repo, self._limits)
        self._planner = PlannerService(repo, self._limits)

    @property
    def repo(self) -> BrainV3Repository:
        return self._repo

    def _note_error(self, exc: BaseException) -> None:
        self.last_error = str(exc)

    # ── Graph ─────────────────────────────────────────────────────────────

    def create_entity(self, data: Mapping[str, Any]) -> Entity:
        try:
            return self._graph.create_entity(data)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def update_entity(self, entity_id: str, updates: Mapping[str, Any]) -> Entity:
        try:
            return self._graph.update_entity(entity_id, updates)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def get_entity(self, entity_id: str) -> Entity:
        return self._graph.get_entity(entity_id)

    def find_entities(
        self,
        *,
        query: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        tokens = _tokenize(query or "")
        entities = self._graph.list_entities(
            entity_type=entity_type,
            status=status,
            limit=self._limits.max_batch_size,
            offset=0,
        )
        if tokens:
            entities = [entity for entity in entities if _entity_matches(entity, tokens)]
        start = max(0, offset)
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return entities[start : start + bounded]

    def create_relation(self, data: Mapping[str, Any]) -> Relation:
        try:
            return self._graph.create_relation(data)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def remove_relation(self, relation_id: str) -> Relation:
        try:
            return self._graph.remove_relation(relation_id)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def get_neighbors(
        self,
        entity_id: str,
        *,
        limit: int = 100,
    ) -> List[Tuple[Entity, Relation]]:
        return self._graph.find_neighbors(entity_id, limit=limit)

    def traverse(
        self,
        start_id: str,
        *,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._graph.traverse(start_id, max_depth=max_depth, max_nodes=max_nodes)

    # ── Timeline ──────────────────────────────────────────────────────────

    def record_timeline_event(self, data: Mapping[str, Any]) -> TimelineEvent:
        try:
            return self._timeline.record_event(data)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def get_timeline(
        self,
        *,
        entity_id: Optional[str] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TimelineEvent]:
        return self._timeline.list_events(
            limit=limit,
            offset=offset,
            entity_id=entity_id,
            time_from=time_from,
            time_to=time_to,
        )

    # ── Retrieval ─────────────────────────────────────────────────────────

    def retrieve_context(
        self,
        query: str,
        *,
        entity_types: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        min_confidence: float = 0.0,
        max_results: Optional[int] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        return _retrieve_context(
            self._repo,
            query,
            entity_types=entity_types,
            project_id=project_id,
            min_confidence=min_confidence,
            max_results=max_results,
            time_from=time_from,
            time_to=time_to,
            limits=self._limits,
        )

    # ── Planner ───────────────────────────────────────────────────────────

    def create_plan(self, data: Mapping[str, Any]) -> Plan:
        if not isinstance(data, Mapping):
            raise ValidationError("plan payload must be a mapping")
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError("title required")
        goal_entity_id = data.get("goal_entity_id")
        raw_steps = data.get("steps") or []
        if not isinstance(raw_steps, list):
            raise ValidationError("steps must be a list")
        step_titles: List[str] = []
        for item in raw_steps:
            if isinstance(item, str):
                step_titles.append(item)
            elif isinstance(item, Mapping):
                step_titles.append(str(item.get("title") or ""))
            else:
                raise ValidationError("each step must be a string or mapping")
        meta = {
            key: data[key]
            for key in (
                "assumptions",
                "constraints",
                "risks",
                "approval_points",
                "verification_steps",
                "rollback_notes",
                "source_id",
                "confidence",
            )
            if key in data
        }
        try:
            return self._planner.create_plan(goal_entity_id, title, step_titles, **meta)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def get_plan(self, plan_id: str) -> Plan:
        return self._planner.get_plan(plan_id)

    # ── Controlled ingestion ──────────────────────────────────────────────

    def _build_ingest_candidates(
        self,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValidationError("ingest payload must be a mapping")

        source_data = _require_dict(payload, "source")
        if not source_data:
            raise ValidationError("source required for ingestion")

        source_type = source_data.get("source_type")
        source_reference = source_data.get("source_reference")
        if not source_type or not source_reference:
            raise ValidationError("source.source_type and source.source_reference required")

        content = str(source_data.get("content") or source_reference)
        source_candidate = build_source_record(
            {
                "id": source_data.get("id") or new_id("src"),
                "source_type": source_type,
                "source_reference": source_reference,
                "content_hash": source_data.get("content_hash") or content_hash(content),
                "captured_at": source_data.get("captured_at"),
                "trust_level": source_data.get("trust_level", 0.5),
                "metadata": source_data.get("metadata") or {},
            },
            self._limits,
        )

        entity_candidates: List[Dict[str, Any]] = []
        relation_candidates: List[Dict[str, Any]] = []
        timeline_candidates: List[Dict[str, Any]] = []
        warnings: List[str] = []
        errors: List[str] = []

        for index, raw_entity in enumerate(_require_list(payload, "entities")):
            if not isinstance(raw_entity, Mapping):
                errors.append(f"entities[{index}] must be a dict")
                continue
            entity_data = dict(raw_entity)
            if entity_data.get("source_id") is None:
                entity_data["source_id"] = source_candidate.id
            try:
                entity = build_entity(entity_data, self._limits)
            except ValidationError as exc:
                errors.append(f"entities[{index}]: {exc}")
                continue
            existing = self._repo.find_entity_by_canonical(entity.entity_type, entity.canonical_name)
            action = "create"
            if existing is not None and existing.status == "active":
                action = "conflict"
                warnings.append(
                    f"entity {entity.entity_type}/{entity.canonical_name} already exists as {existing.id}"
                )
            entity_candidates.append(
                {
                    "action": action,
                    "candidate": entity.to_dict(),
                    "existing_id": existing.id if existing is not None else None,
                }
            )

        known_entity_ids = {
            item["candidate"]["id"]
            for item in entity_candidates
            if item["action"] != "conflict"
        }
        for item in entity_candidates:
            if item["existing_id"]:
                known_entity_ids.add(item["existing_id"])

        for index, raw_relation in enumerate(_require_list(payload, "relations")):
            if not isinstance(raw_relation, Mapping):
                errors.append(f"relations[{index}] must be a dict")
                continue
            relation_data = dict(raw_relation)
            if relation_data.get("source_id") is None:
                relation_data["source_id"] = source_candidate.id
            try:
                relation = build_relation(relation_data, self._limits)
            except ValidationError as exc:
                errors.append(f"relations[{index}]: {exc}")
                continue
            missing = [
                eid
                for eid in (relation.source_entity_id, relation.target_entity_id)
                if eid not in known_entity_ids
            ]
            for eid in missing:
                try:
                    self._repo.get_entity(eid)
                    known_entity_ids.add(eid)
                except Exception:
                    errors.append(f"relations[{index}]: unknown entity {eid}")
            relation_candidates.append({"action": "create", "candidate": relation.to_dict()})

        events_key = "timeline_events"
        if events_key not in payload and "events" in payload:
            events_key = "events"
        for index, raw_event in enumerate(_require_list(payload, events_key)):
            if not isinstance(raw_event, Mapping):
                errors.append(f"{events_key}[{index}] must be a dict")
                continue
            event_data = dict(raw_event)
            if event_data.get("source_id") is None:
                event_data["source_id"] = source_candidate.id
            try:
                event = build_timeline_event(event_data, self._limits)
            except ValidationError as exc:
                errors.append(f"{events_key}[{index}]: {exc}")
                continue
            for eid in event.entity_ids:
                if eid not in known_entity_ids:
                    try:
                        self._repo.get_entity(eid)
                        known_entity_ids.add(eid)
                    except Exception:
                        errors.append(f"{events_key}[{index}]: unknown entity {eid}")
            timeline_candidates.append({"action": "create", "candidate": event.to_dict()})

        valid = not errors
        return {
            "dry_run": True,
            "committed": False,
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "source": source_candidate.to_dict(),
            "entities": entity_candidates,
            "relations": relation_candidates,
            "timeline_events": timeline_candidates,
        }

    def ingest_preview(self, payload: dict) -> Dict[str, Any]:
        """Validate ingestion payload and return candidates without writing."""
        try:
            return self._build_ingest_candidates(payload)
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

    def ingest_commit(self, payload: dict, *, confirm: bool = False) -> Dict[str, Any]:
        """Preview by default; write only when ``confirm=True``."""
        preview = self._build_ingest_candidates(payload)
        if not confirm:
            return preview
        if not preview["valid"]:
            raise ValidationError("ingest payload invalid; fix errors before commit")
        if self._repo.read_only:
            raise ValidationError("repository is read-only")

        created: Dict[str, Any] = {
            "source": None,
            "entities": [],
            "relations": [],
            "timeline_events": [],
        }

        try:
            source = build_source_record(preview["source"], self._limits)
            created["source"] = self._provenance.record_source(
                source.source_type,
                source.source_reference,
                content_hash_value=source.content_hash,
                trust_level=source.trust_level,
                metadata=source.metadata,
                source_id=source.id,
                captured_at=source.captured_at,
            ).to_dict()

            id_map: Dict[str, str] = {}
            for item in preview["entities"]:
                if item["action"] == "conflict":
                    if item["existing_id"]:
                        id_map[item["candidate"]["id"]] = item["existing_id"]
                    continue
                stored = self._graph.create_entity(item["candidate"])
                id_map[item["candidate"]["id"]] = stored.id
                created["entities"].append(stored.to_dict())

            def _resolve_entity_id(entity_id: str) -> str:
                return id_map.get(entity_id, entity_id)

            for item in preview["relations"]:
                relation_data = dict(item["candidate"])
                relation_data["source_entity_id"] = _resolve_entity_id(
                    relation_data["source_entity_id"]
                )
                relation_data["target_entity_id"] = _resolve_entity_id(
                    relation_data["target_entity_id"]
                )
                stored = self._graph.create_relation(relation_data)
                created["relations"].append(stored.to_dict())

            for item in preview["timeline_events"]:
                event_data = dict(item["candidate"])
                event_data["entity_ids"] = [
                    _resolve_entity_id(eid) for eid in event_data.get("entity_ids") or []
                ]
                stored = self._timeline.record_event(event_data)
                created["timeline_events"].append(stored.to_dict())
        except BrainV3Error as exc:
            self._note_error(exc)
            raise

        return {
            "dry_run": False,
            "committed": True,
            "valid": True,
            "errors": [],
            "warnings": preview["warnings"],
            "created": created,
        }

    # ── Diagnostics / lifecycle ───────────────────────────────────────────

    def get_diagnostics(self) -> Diagnostics:
        return gather_diagnostics(self)

    def close(self) -> None:
        self._repo.close()


def create_brain_v3(
    *,
    enabled: bool = False,
    root_dir: Optional[_PathLike] = None,
    limits: BrainV3Limits | None = None,
    read_only: bool = False,
) -> Optional[BrainV3Service]:
    """Return a service when ``enabled``, else ``None`` with zero I/O."""
    if not enabled:
        return None

    lim = limits or BrainV3Limits()
    root = _resolve_root(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "brain_v3.db"
    repo = BrainV3Repository(db_path, lim, read_only=read_only)
    return BrainV3Service(repo, enabled=True, limits=lim)
