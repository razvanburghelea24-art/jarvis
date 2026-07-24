"""Brain V3 SQLite schema (Phase 1)."""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id               TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    captured_at      TEXT NOT NULL,
    trust_level      REAL NOT NULL DEFAULT 0.5,
    metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sources_source_type ON sources(source_type);
CREATE INDEX IF NOT EXISTS idx_sources_captured_at ON sources(captured_at);

CREATE TABLE IF NOT EXISTS entities (
    id                  TEXT PRIMARY KEY,
    entity_type         TEXT NOT NULL,
    canonical_name      TEXT NOT NULL,
    display_name        TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    attributes_json     TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    source_id           TEXT REFERENCES sources(id) ON DELETE SET NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    confidence_category TEXT NOT NULL DEFAULT 'user_stated',
    status              TEXT NOT NULL DEFAULT 'active',
    aliases_json        TEXT NOT NULL DEFAULT '[]',
    UNIQUE(entity_type, canonical_name)
);

CREATE INDEX IF NOT EXISTS idx_entities_entity_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_canonical_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_source_id ON entities(source_id);

CREATE TABLE IF NOT EXISTS relations (
    id               TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type    TEXT NOT NULL,
    target_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    attributes_json  TEXT NOT NULL DEFAULT '{}',
    source_id        TEXT REFERENCES sources(id) ON DELETE SET NULL,
    confidence       REAL NOT NULL DEFAULT 0.5,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    UNIQUE(source_entity_id, relation_type, target_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_relations_source_entity ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target_entity ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_relation_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_status ON relations(status);
CREATE INDEX IF NOT EXISTS idx_relations_source_id ON relations(source_id);

CREATE TABLE IF NOT EXISTS timeline_events (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    occurred_at     TEXT NOT NULL,
    recorded_at     TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    source_id       TEXT REFERENCES sources(id) ON DELETE SET NULL,
    confidence      REAL NOT NULL DEFAULT 0.5,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    dedupe_hash     TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_timeline_occurred_at ON timeline_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_timeline_event_type ON timeline_events(event_type);
CREATE INDEX IF NOT EXISTS idx_timeline_source_id ON timeline_events(source_id);

CREATE TABLE IF NOT EXISTS timeline_entity (
    event_id  TEXT NOT NULL REFERENCES timeline_events(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_timeline_entity_entity_id ON timeline_entity(entity_id);

CREATE TABLE IF NOT EXISTS plans (
    id                      TEXT PRIMARY KEY,
    goal_entity_id          TEXT REFERENCES entities(id) ON DELETE SET NULL,
    title                   TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'draft',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    source_id               TEXT REFERENCES sources(id) ON DELETE SET NULL,
    confidence              REAL NOT NULL DEFAULT 0.5,
    assumptions_json        TEXT NOT NULL DEFAULT '[]',
    constraints_json        TEXT NOT NULL DEFAULT '[]',
    risks_json              TEXT NOT NULL DEFAULT '[]',
    approval_points_json    TEXT NOT NULL DEFAULT '[]',
    verification_steps_json TEXT NOT NULL DEFAULT '[]',
    rollback_notes_json     TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_goal_entity_id ON plans(goal_entity_id);
CREATE INDEX IF NOT EXISTS idx_plans_source_id ON plans(source_id);

CREATE TABLE IF NOT EXISTS plan_steps (
    id                  TEXT PRIMARY KEY,
    plan_id             TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    order_index         INTEGER NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    dependencies_json   TEXT NOT NULL DEFAULT '[]',
    risk_level          TEXT NOT NULL DEFAULT 'low',
    requires_approval   INTEGER NOT NULL DEFAULT 1,
    execution_forbidden INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_plan_steps_plan_id ON plan_steps(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_steps_status ON plan_steps(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_plan_steps_plan_order ON plan_steps(plan_id, order_index);

CREATE TABLE IF NOT EXISTS conflicts (
    id                    TEXT PRIMARY KEY,
    entity_id             TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    field                 TEXT NOT NULL,
    value_a               TEXT NOT NULL,
    value_b               TEXT NOT NULL,
    source_a              TEXT REFERENCES sources(id) ON DELETE SET NULL,
    source_b              TEXT REFERENCES sources(id) ON DELETE SET NULL,
    created_at            TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'open',
    requires_confirmation INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_conflicts_entity_id ON conflicts(entity_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

REQUIRED_TABLES = (
    "meta",
    "sources",
    "entities",
    "relations",
    "timeline_events",
    "timeline_entity",
    "plans",
    "plan_steps",
    "conflicts",
    "schema_migrations",
)
