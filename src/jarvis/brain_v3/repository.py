"""Brain V3 SQLite repository."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .config import SCHEMA_VERSION
from .errors import LimitExceededError, NotFoundError, SchemaError
from .limits import BrainV3Limits
from .migrations import migrate
from .models import (
    ConflictRecord,
    Entity,
    Plan,
    PlanStep,
    Relation,
    SourceRecord,
    TimelineEvent,
    content_hash,
    dumps_json,
)
from .schema import SCHEMA_VERSION as DDL_SCHEMA_VERSION


def _loads_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _timeline_dedupe_hash(event: TimelineEvent) -> str:
    payload = dumps_json(
        {
            "event_type": event.event_type,
            "title": event.title,
            "occurred_at": event.occurred_at,
            "entity_ids": sorted(event.entity_ids),
        }
    )
    return content_hash(payload)


class BrainV3Repository:
    """Thread-safe SQLite persistence for Brain V3."""

    def __init__(
        self,
        db_path: Path | str,
        limits: BrainV3Limits,
        *,
        read_only: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.limits = limits
        self.read_only = read_only
        self._lock = threading.RLock()

        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if read_only:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            self.conn = sqlite3.connect(
                uri,
                uri=True,
                check_same_thread=False,
                timeout=5,
            )
        else:
            self.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=5,
            )

        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA foreign_keys = ON")
            if not read_only:
                applied = migrate(self.conn)
                if applied != SCHEMA_VERSION:
                    raise SchemaError(
                        f"unexpected schema version after migrate: {applied}"
                    )
            else:
                from .migrations import verify_schema

                verify_schema(self.conn)

        if DDL_SCHEMA_VERSION != SCHEMA_VERSION:
            raise SchemaError("schema module version mismatch with config")

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._ensure_writable()
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise SchemaError("repository is read-only")

    def _assert_under_limit(self, table: str, max_count: int, incoming: int = 1) -> None:
        current = self._count_table(table)
        if current + incoming > max_count:
            raise LimitExceededError(f"{table} limit exceeded ({max_count})")

    def _count_table(self, table: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"]) if row else 0

    # ── Counts ────────────────────────────────────────────────────────────

    def count_sources(self) -> int:
        with self._lock:
            return self._count_table("sources")

    def count_entities(self) -> int:
        with self._lock:
            return self._count_table("entities")

    def count_relations(self) -> int:
        with self._lock:
            return self._count_table("relations")

    def count_timeline_events(self) -> int:
        with self._lock:
            return self._count_table("timeline_events")

    def count_plans(self) -> int:
        with self._lock:
            return self._count_table("plans")

    def count_plan_steps(self) -> int:
        with self._lock:
            return self._count_table("plan_steps")

    def count_conflicts(self) -> int:
        with self._lock:
            return self._count_table("conflicts")

    # ── Sources ───────────────────────────────────────────────────────────

    def create_source(self, source: SourceRecord) -> SourceRecord:
        self._ensure_writable()
        with self.transaction():
            self._assert_under_limit("sources", self.limits.max_sources)
            self.conn.execute(
                """
                INSERT INTO sources (
                    id, source_type, source_reference, content_hash,
                    captured_at, trust_level, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.source_type,
                    source.source_reference,
                    source.content_hash,
                    source.captured_at,
                    source.trust_level,
                    dumps_json(source.metadata),
                ),
            )
        return source

    def get_source(self, source_id: str) -> SourceRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"source not found: {source_id}")
        return self._row_to_source(row)

    def update_source(self, source: SourceRecord) -> SourceRecord:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE sources SET
                    source_type = ?,
                    source_reference = ?,
                    content_hash = ?,
                    captured_at = ?,
                    trust_level = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    source.source_type,
                    source.source_reference,
                    source.content_hash,
                    source.captured_at,
                    source.trust_level,
                    dumps_json(source.metadata),
                    source.id,
                ),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"source not found: {source.id}")
        return source

    def delete_source(self, source_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"source not found: {source_id}")

    def list_sources(self, *, limit: int = 100, offset: int = 0) -> List[SourceRecord]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM sources
                ORDER BY captured_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._row_to_source(row) for row in rows]

    # ── Entities ──────────────────────────────────────────────────────────

    def create_entity(self, entity: Entity) -> Entity:
        self._ensure_writable()
        with self.transaction():
            self._assert_under_limit("entities", self.limits.max_entities)
            self.conn.execute(
                """
                INSERT INTO entities (
                    id, entity_type, canonical_name, display_name, description,
                    attributes_json, created_at, updated_at, source_id,
                    confidence, confidence_category, status, aliases_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._entity_params(entity),
            )
        return entity

    def batch_insert_entities(self, entities: Sequence[Entity]) -> List[Entity]:
        if not entities:
            return []
        self._ensure_writable()
        batch_size = min(len(entities), self.limits.max_batch_size)
        if len(entities) > batch_size:
            raise LimitExceededError(
                f"batch size {len(entities)} exceeds max_batch_size ({batch_size})"
            )
        with self.transaction():
            self._assert_under_limit("entities", self.limits.max_entities, len(entities))
            self.conn.executemany(
                """
                INSERT INTO entities (
                    id, entity_type, canonical_name, display_name, description,
                    attributes_json, created_at, updated_at, source_id,
                    confidence, confidence_category, status, aliases_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._entity_params(entity) for entity in entities],
            )
        return list(entities)

    def get_entity(self, entity_id: str) -> Entity:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return self._row_to_entity(row)

    def find_entity_by_canonical(
        self,
        entity_type: str,
        canonical_name: str,
    ) -> Optional[Entity]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT * FROM entities
                WHERE entity_type = ? AND canonical_name = ?
                LIMIT 1
                """,
                (entity_type, canonical_name),
            ).fetchone()
        return self._row_to_entity(row) if row else None

    def list_entities(
        self,
        *,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        clauses: List[str] = []
        params: List[Any] = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM entities
                {where}
                ORDER BY canonical_name ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def update_entity(self, entity: Entity) -> Entity:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE entities SET
                    entity_type = ?,
                    canonical_name = ?,
                    display_name = ?,
                    description = ?,
                    attributes_json = ?,
                    created_at = ?,
                    updated_at = ?,
                    source_id = ?,
                    confidence = ?,
                    confidence_category = ?,
                    status = ?,
                    aliases_json = ?
                WHERE id = ?
                """,
                self._entity_params(entity)[1:] + (entity.id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"entity not found: {entity.id}")
        return entity

    def delete_entity(self, entity_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"entity not found: {entity_id}")

    def neighbors(
        self,
        entity_id: str,
        *,
        limit: Optional[int] = None,
    ) -> List[Tuple[Entity, Relation]]:
        cap = limit if limit is not None else self.limits.max_retrieval_results
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT
                    e.*,
                    r.id AS rel_id,
                    r.source_entity_id,
                    r.relation_type,
                    r.target_entity_id,
                    r.attributes_json AS rel_attributes_json,
                    r.source_id AS rel_source_id,
                    r.confidence AS rel_confidence,
                    r.created_at AS rel_created_at,
                    r.updated_at AS rel_updated_at,
                    r.status AS rel_status
                FROM relations r
                JOIN entities e ON e.id = CASE
                    WHEN r.source_entity_id = ? THEN r.target_entity_id
                    ELSE r.source_entity_id
                END
                WHERE (r.source_entity_id = ? OR r.target_entity_id = ?)
                  AND r.status = 'active'
                ORDER BY r.updated_at DESC, r.id ASC
                LIMIT ?
                """,
                (entity_id, entity_id, entity_id, cap),
            ).fetchall()
        out: List[Tuple[Entity, Relation]] = []
        for row in rows:
            entity = self._row_to_entity(row)
            relation = Relation(
                id=row["rel_id"],
                source_entity_id=row["source_entity_id"],
                relation_type=row["relation_type"],
                target_entity_id=row["target_entity_id"],
                attributes=_loads_json(row["rel_attributes_json"], {}),
                source_id=row["rel_source_id"],
                confidence=float(row["rel_confidence"]),
                created_at=row["rel_created_at"],
                updated_at=row["rel_updated_at"],
                status=row["rel_status"],
            )
            out.append((entity, relation))
        return out

    # ── Relations ─────────────────────────────────────────────────────────

    def create_relation(self, relation: Relation) -> Relation:
        self._ensure_writable()
        with self.transaction():
            self._assert_under_limit("relations", self.limits.max_relations)
            self.conn.execute(
                """
                INSERT INTO relations (
                    id, source_entity_id, relation_type, target_entity_id,
                    attributes_json, source_id, confidence,
                    created_at, updated_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._relation_params(relation),
            )
        return relation

    def get_relation(self, relation_id: str) -> Relation:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM relations WHERE id = ?",
                (relation_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"relation not found: {relation_id}")
        return self._row_to_relation(row)

    def update_relation(self, relation: Relation) -> Relation:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE relations SET
                    source_entity_id = ?,
                    relation_type = ?,
                    target_entity_id = ?,
                    attributes_json = ?,
                    source_id = ?,
                    confidence = ?,
                    created_at = ?,
                    updated_at = ?,
                    status = ?
                WHERE id = ?
                """,
                self._relation_params(relation)[1:] + (relation.id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"relation not found: {relation.id}")
        return relation

    def delete_relation(self, relation_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                "DELETE FROM relations WHERE id = ?",
                (relation_id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"relation not found: {relation_id}")

    def list_relations(
        self,
        *,
        source_entity_id: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Relation]:
        clauses: List[str] = []
        params: List[Any] = []
        if source_entity_id is not None:
            clauses.append("source_entity_id = ?")
            params.append(source_entity_id)
        if target_entity_id is not None:
            clauses.append("target_entity_id = ?")
            params.append(target_entity_id)
        if relation_type is not None:
            clauses.append("relation_type = ?")
            params.append(relation_type)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM relations
                {where}
                ORDER BY updated_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_relation(row) for row in rows]

    # ── Timeline ──────────────────────────────────────────────────────────

    def create_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        self._ensure_writable()
        dedupe = _timeline_dedupe_hash(event)
        with self.transaction():
            self._assert_under_limit("timeline_events", self.limits.max_timeline_events)
            self.conn.execute(
                """
                INSERT INTO timeline_events (
                    id, event_type, title, description, occurred_at, recorded_at,
                    entity_ids_json, source_id, confidence, metadata_json, dedupe_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type,
                    event.title,
                    event.description,
                    event.occurred_at,
                    event.recorded_at,
                    dumps_json(event.entity_ids),
                    event.source_id,
                    event.confidence,
                    dumps_json(event.metadata),
                    dedupe,
                ),
            )
            self._sync_timeline_entities(event.id, event.entity_ids)
        return event

    def get_timeline_event(self, event_id: str) -> TimelineEvent:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM timeline_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"timeline event not found: {event_id}")
        return self._row_to_timeline_event(row)

    def update_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        self._ensure_writable()
        dedupe = _timeline_dedupe_hash(event)
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE timeline_events SET
                    event_type = ?,
                    title = ?,
                    description = ?,
                    occurred_at = ?,
                    recorded_at = ?,
                    entity_ids_json = ?,
                    source_id = ?,
                    confidence = ?,
                    metadata_json = ?,
                    dedupe_hash = ?
                WHERE id = ?
                """,
                (
                    event.event_type,
                    event.title,
                    event.description,
                    event.occurred_at,
                    event.recorded_at,
                    dumps_json(event.entity_ids),
                    event.source_id,
                    event.confidence,
                    dumps_json(event.metadata),
                    dedupe,
                    event.id,
                ),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"timeline event not found: {event.id}")
            self.conn.execute(
                "DELETE FROM timeline_entity WHERE event_id = ?",
                (event.id,),
            )
            self._sync_timeline_entities(event.id, event.entity_ids)
        return event

    def delete_timeline_event(self, event_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                "DELETE FROM timeline_events WHERE id = ?",
                (event_id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"timeline event not found: {event_id}")

    def list_timeline_events(
        self,
        *,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TimelineEvent]:
        clauses: List[str] = []
        params: List[Any] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM timeline_events
                {where}
                ORDER BY occurred_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_timeline_event(row) for row in rows]

    def _sync_timeline_entities(self, event_id: str, entity_ids: Sequence[str]) -> None:
        for entity_id in entity_ids:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO timeline_entity (event_id, entity_id)
                VALUES (?, ?)
                """,
                (event_id, entity_id),
            )

    # ── Plans ─────────────────────────────────────────────────────────────

    def create_plan(self, plan: Plan) -> Plan:
        self._ensure_writable()
        with self.transaction():
            self._assert_under_limit("plans", self.limits.max_plans)
            if plan.steps:
                self._assert_under_limit(
                    "plan_steps",
                    self.limits.max_plan_steps,
                    len(plan.steps),
                )
            self.conn.execute(
                """
                INSERT INTO plans (
                    id, goal_entity_id, title, status, created_at, updated_at,
                    source_id, confidence, assumptions_json, constraints_json,
                    risks_json, approval_points_json, verification_steps_json,
                    rollback_notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._plan_params(plan),
            )
            for step in plan.steps:
                self._insert_plan_step(step)
        return plan

    def get_plan(self, plan_id: str) -> Plan:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"plan not found: {plan_id}")
            step_rows = self.conn.execute(
                """
                SELECT * FROM plan_steps
                WHERE plan_id = ?
                ORDER BY order_index ASC, id ASC
                """,
                (plan_id,),
            ).fetchall()
        plan = self._row_to_plan(row)
        plan.steps = [self._row_to_plan_step(r) for r in step_rows]
        return plan

    def update_plan(self, plan: Plan) -> Plan:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE plans SET
                    goal_entity_id = ?,
                    title = ?,
                    status = ?,
                    created_at = ?,
                    updated_at = ?,
                    source_id = ?,
                    confidence = ?,
                    assumptions_json = ?,
                    constraints_json = ?,
                    risks_json = ?,
                    approval_points_json = ?,
                    verification_steps_json = ?,
                    rollback_notes_json = ?
                WHERE id = ?
                """,
                self._plan_params(plan)[1:] + (plan.id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"plan not found: {plan.id}")
        return plan

    def delete_plan(self, plan_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"plan not found: {plan_id}")

    def list_plans(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Plan]:
        clauses: List[str] = []
        params: List[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM plans
                {where}
                ORDER BY updated_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_plan(row) for row in rows]

    def create_plan_step(self, step: PlanStep) -> PlanStep:
        self._ensure_writable()
        with self.transaction():
            self._assert_under_limit("plan_steps", self.limits.max_plan_steps)
            self._insert_plan_step(step)
        return step

    def get_plan_step(self, step_id: str) -> PlanStep:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM plan_steps WHERE id = ?",
                (step_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"plan step not found: {step_id}")
        return self._row_to_plan_step(row)

    def update_plan_step(self, step: PlanStep) -> PlanStep:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE plan_steps SET
                    plan_id = ?,
                    order_index = ?,
                    title = ?,
                    description = ?,
                    status = ?,
                    dependencies_json = ?,
                    risk_level = ?,
                    requires_approval = ?,
                    execution_forbidden = ?
                WHERE id = ?
                """,
                self._plan_step_params(step)[1:] + (step.id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"plan step not found: {step.id}")
        return step

    def delete_plan_step(self, step_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                "DELETE FROM plan_steps WHERE id = ?",
                (step_id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"plan step not found: {step_id}")

    def list_plan_steps(self, plan_id: str) -> List[PlanStep]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM plan_steps
                WHERE plan_id = ?
                ORDER BY order_index ASC, id ASC
                """,
                (plan_id,),
            ).fetchall()
        return [self._row_to_plan_step(row) for row in rows]

    def _insert_plan_step(self, step: PlanStep) -> None:
        self.conn.execute(
            """
            INSERT INTO plan_steps (
                id, plan_id, order_index, title, description, status,
                dependencies_json, risk_level, requires_approval, execution_forbidden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._plan_step_params(step),
        )

    # ── Conflicts ─────────────────────────────────────────────────────────

    def create_conflict(self, conflict: ConflictRecord) -> ConflictRecord:
        self._ensure_writable()
        with self.transaction():
            self.conn.execute(
                """
                INSERT INTO conflicts (
                    id, entity_id, field, value_a, value_b,
                    source_a, source_b, created_at, status, requires_confirmation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._conflict_params(conflict),
            )
        return conflict

    def get_conflict(self, conflict_id: str) -> ConflictRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM conflicts WHERE id = ?",
                (conflict_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"conflict not found: {conflict_id}")
        return self._row_to_conflict(row)

    def update_conflict(self, conflict: ConflictRecord) -> ConflictRecord:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                """
                UPDATE conflicts SET
                    entity_id = ?,
                    field = ?,
                    value_a = ?,
                    value_b = ?,
                    source_a = ?,
                    source_b = ?,
                    created_at = ?,
                    status = ?,
                    requires_confirmation = ?
                WHERE id = ?
                """,
                self._conflict_params(conflict)[1:] + (conflict.id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"conflict not found: {conflict.id}")
        return conflict

    def delete_conflict(self, conflict_id: str) -> None:
        self._ensure_writable()
        with self.transaction():
            cur = self.conn.execute(
                "DELETE FROM conflicts WHERE id = ?",
                (conflict_id,),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"conflict not found: {conflict_id}")

    def list_conflicts(
        self,
        *,
        entity_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ConflictRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM conflicts
                {where}
                ORDER BY created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_conflict(row) for row in rows]

    # ── Row mappers ───────────────────────────────────────────────────────

    @staticmethod
    def _entity_params(entity: Entity) -> Tuple[Any, ...]:
        return (
            entity.id,
            entity.entity_type,
            entity.canonical_name,
            entity.display_name,
            entity.description,
            dumps_json(entity.attributes),
            entity.created_at,
            entity.updated_at,
            entity.source_id,
            entity.confidence,
            entity.confidence_category,
            entity.status,
            dumps_json(entity.aliases),
        )

    @staticmethod
    def _relation_params(relation: Relation) -> Tuple[Any, ...]:
        return (
            relation.id,
            relation.source_entity_id,
            relation.relation_type,
            relation.target_entity_id,
            dumps_json(relation.attributes),
            relation.source_id,
            relation.confidence,
            relation.created_at,
            relation.updated_at,
            relation.status,
        )

    @staticmethod
    def _plan_params(plan: Plan) -> Tuple[Any, ...]:
        return (
            plan.id,
            plan.goal_entity_id,
            plan.title,
            plan.status,
            plan.created_at,
            plan.updated_at,
            plan.source_id,
            plan.confidence,
            dumps_json(plan.assumptions),
            dumps_json(plan.constraints),
            dumps_json(plan.risks),
            dumps_json(plan.approval_points),
            dumps_json(plan.verification_steps),
            dumps_json(plan.rollback_notes),
        )

    @staticmethod
    def _plan_step_params(step: PlanStep) -> Tuple[Any, ...]:
        return (
            step.id,
            step.plan_id,
            step.order_index,
            step.title,
            step.description,
            step.status,
            dumps_json(step.dependencies),
            step.risk_level,
            1 if step.requires_approval else 0,
            1 if step.execution_forbidden else 0,
        )

    @staticmethod
    def _conflict_params(conflict: ConflictRecord) -> Tuple[Any, ...]:
        return (
            conflict.id,
            conflict.entity_id,
            conflict.field,
            conflict.value_a,
            conflict.value_b,
            conflict.source_a,
            conflict.source_b,
            conflict.created_at,
            conflict.status,
            1 if conflict.requires_confirmation else 0,
        )

    @staticmethod
    def _row_to_source(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            id=row["id"],
            source_type=row["source_type"],
            source_reference=row["source_reference"],
            content_hash=row["content_hash"],
            captured_at=row["captured_at"],
            trust_level=float(row["trust_level"]),
            metadata=_loads_json(row["metadata_json"], {}),
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            display_name=row["display_name"],
            description=row["description"],
            attributes=_loads_json(row["attributes_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_id=row["source_id"],
            confidence=float(row["confidence"]),
            confidence_category=row["confidence_category"],
            status=row["status"],
            aliases=_loads_json(row["aliases_json"], []),
        )

    @staticmethod
    def _row_to_relation(row: sqlite3.Row) -> Relation:
        return Relation(
            id=row["id"],
            source_entity_id=row["source_entity_id"],
            relation_type=row["relation_type"],
            target_entity_id=row["target_entity_id"],
            attributes=_loads_json(row["attributes_json"], {}),
            source_id=row["source_id"],
            confidence=float(row["confidence"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
        )

    @staticmethod
    def _row_to_timeline_event(row: sqlite3.Row) -> TimelineEvent:
        return TimelineEvent(
            id=row["id"],
            event_type=row["event_type"],
            title=row["title"],
            description=row["description"],
            occurred_at=row["occurred_at"],
            recorded_at=row["recorded_at"],
            entity_ids=_loads_json(row["entity_ids_json"], []),
            source_id=row["source_id"],
            confidence=float(row["confidence"]),
            metadata=_loads_json(row["metadata_json"], {}),
        )

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> Plan:
        return Plan(
            id=row["id"],
            goal_entity_id=row["goal_entity_id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_id=row["source_id"],
            confidence=float(row["confidence"]),
            assumptions=_loads_json(row["assumptions_json"], []),
            constraints=_loads_json(row["constraints_json"], []),
            risks=_loads_json(row["risks_json"], []),
            approval_points=_loads_json(row["approval_points_json"], []),
            verification_steps=_loads_json(row["verification_steps_json"], []),
            rollback_notes=_loads_json(row["rollback_notes_json"], []),
            steps=[],
        )

    @staticmethod
    def _row_to_plan_step(row: sqlite3.Row) -> PlanStep:
        return PlanStep(
            id=row["id"],
            plan_id=row["plan_id"],
            order_index=int(row["order_index"]),
            title=row["title"],
            description=row["description"],
            status=row["status"],
            dependencies=_loads_json(row["dependencies_json"], []),
            risk_level=row["risk_level"],
            requires_approval=bool(row["requires_approval"]),
            execution_forbidden=bool(row["execution_forbidden"]),
        )

    @staticmethod
    def _row_to_conflict(row: sqlite3.Row) -> ConflictRecord:
        return ConflictRecord(
            id=row["id"],
            entity_id=row["entity_id"],
            field=row["field"],
            value_a=row["value_a"],
            value_b=row["value_b"],
            source_a=row["source_a"],
            source_b=row["source_b"],
            created_at=row["created_at"],
            status=row["status"],
            requires_confirmation=bool(row["requires_confirmation"]),
        )
