# Brain V3 — Phase 1 Cognitive Foundation (internal)

Status: **Phase 1 foundation**. Default **OFF**. Non-executable planner.
Controlled ingestion defaults to **dry-run**. No H / shell / network / Git
authority. Not wired into `reply.engine` or the daemon unless explicitly
integrated later.

## Purpose

Brain V3 sits above Brain Memory v2 as a **semantic / cognitive layer**:

| Capability | Phase 1 behaviour |
|------------|-------------------|
| Knowledge graph | Entities, relations, bounded traversal |
| Timeline | Project/decision/event history with dedupe |
| Context retrieval | Read-only, bounded, explainable |
| Planner | Structured plans; **every step non-executable** |
| Provenance | Source records, confidence categories |
| Ingestion | Validate → preview → explicit commit |

Brain V2 remains the durable foundation for preferences and projects. Brain V3
does **not** auto-migrate Brain V2 data or modify Brain V2 when Brain V3 is OFF.

## Package layout

Public package exports (`__all__`): `BrainV3Service`, `BrainV3Phase2Service`,
`BrainV3Phase3Service`, `create_brain_v3`, `create_brain_v3_phase2`,
`create_brain_v3_phase3`.

```
src/jarvis/brain_v3/
├── __init__.py          # public exports above
├── config.py            # SCHEMA_VERSION, BrainV3Config
├── models.py            # Entity, Relation, TimelineEvent, Plan, SourceRecord
├── schema.py            # SQLite DDL (version 1)
├── migrations.py        # migrate(), verify_schema(), backup_db_file()
├── repository.py        # BrainV3Repository (thread-safe SQLite; sole sqlite3.connect)
├── graph.py             # GraphService
├── timeline.py          # TimelineService
├── retrieval.py         # retrieve_context() (read-only)
├── planner.py           # PlannerService (non-executable)
├── provenance.py        # ProvenanceService
├── confidence.py        # Category rules and merge helpers
├── validation.py        # Dict → model builders
├── limits.py            # Configurable bounds
├── errors.py            # Typed exceptions
├── diagnostics.py       # gather_diagnostics()
├── service.py           # BrainV3Service facade + create_brain_v3()
├── phase2_service.py    # BrainV3Phase2Service + create_brain_v3_phase2()
├── phase3_service.py    # BrainV3Phase3Service + create_brain_v3_phase3()
├── conversation/        # wired via Phase 2/3 facades
├── extraction/          # wired via Phase 2/3 facades
├── recall/              # Phase 3 approved contextual recall
├── conversational_intelligence/  # Phase 3 answer support
├── memory_proposals/    # Phase 2 proposal workflow
├── project_intelligence/# Phase 2 project snapshots
└── ARCHITECTURE.md      # this file
```

Phase 2/3 live path uses `conversation.build_conversation` +
`extraction.extract_candidates`. Phase 3 recall is **read-only**,
**approved-only**, and **non-executable**. Schema remains **v1** (no Phase 3
DDL); recall filters committed graph rows via `BrainV3Service`.

## OFF behaviour (fail closed)

`create_brain_v3(enabled=False)` returns `None` immediately:

```text
zero mkdir
zero sqlite open
zero migration
zero background thread
zero network / subprocess / shell
```

Callers must treat `None` as “Brain V3 absent”. No lazy initialisation.

When enabled, storage defaults to:

```text
~/.config/jarvis/memory/brain_v3/brain_v3.db
```

(Or under `JARVIS_CONFIG_PATH` / `XDG_CONFIG_HOME` when set.)

## Service layer

`BrainV3Service` wraps:

| Sub-service | Role |
|-------------|------|
| `GraphService` | Entities, relations, traversal |
| `TimelineService` | Events, dedupe, ordering |
| `ProvenanceService` | Immutable source metadata |
| `PlannerService` | Plan CRUD (non-executable steps) |
| `BrainV3Repository` | Persistence |

Public methods are thin, typed delegates. Errors surface as explicit
`BrainV3Error` subclasses; the service records the last error for diagnostics.

### Controlled ingestion

Pipeline:

```text
input dict
  → validation (build_source_record / build_entity / …)
  → normalisation (source_id propagation)
  → entity / relation / timeline candidates
  → ingest_preview()  [always dry-run]
  → ingest_commit(confirm=True)  [explicit write]
```

Defaults:

| Call | Writes? |
|------|---------|
| `ingest_preview(payload)` | Never |
| `ingest_commit(payload)` | Never (`committed=False`) |
| `ingest_commit(payload, confirm=True)` | Yes, single transaction |

Duplicate active entities are reported as conflicts in preview; commit skips
creating duplicates and maps relation endpoints to existing IDs when flagged.

## Non-executable planner

Every `PlanStep` created in Phase 1 has:

```text
requires_approval = true
execution_forbidden = true
```

The planner may create, read, reorder, block, and archive plans. It must **not**
execute steps, spawn agents, write project files, call shell, or activate H.

## Diagnostics

`gather_diagnostics(service_or_repo)` returns counts and health without secrets:

```text
enabled, schema_version, storage_path (basename/relative only),
entity_count, relation_count, timeline_count, plan_count, source_count,
last_migration, last_error, storage_health, read_only_state
```

No raw credentials, absolute home paths, or full source content.

## Rollback runbook

Phase 1 is designed for safe disable and manual recovery.

### 1. Disable live use

Set `brain_v3_enabled = false` (or stop passing `enabled=True` to
`create_brain_v3`). Restart the process. Confirm diagnostics show
`enabled=false` and no new storage files appear.

### 2. Pre-migration backup

Before any schema upgrade in a test harness:

```python
from pathlib import Path
from jarvis.brain_v3.migrations import backup_db_file

backup_db_file(Path("~/.config/jarvis/memory/brain_v3/brain_v3.db"))
```

Creates `brain_v3.db.bak` alongside the database.

### 3. Corruption or failed migration

1. Stop the process.
2. Copy `brain_v3.db.bak` over `brain_v3.db` (or delete the DB to start fresh
   in a non-production harness).
3. Keep Brain V3 OFF until `verify_schema()` passes on the restored file.
4. Re-run migrations only with Brain V3 enabled in an isolated environment.

### 4. Read-only inspection

Open with `read_only=True` on `BrainV3Repository` / `create_brain_v3` for
forensics without writes. Diagnostics will show `read_only_state=true`.

### 5. Complete removal (harness / dev only)

With Brain V3 OFF and no running process holding the file:

```text
remove ~/.config/jarvis/memory/brain_v3/brain_v3.db
remove ~/.config/jarvis/memory/brain_v3/brain_v3.db.bak   # optional
```

Brain V2 JSON stores and H state are unaffected.

## Isolation guarantees (Phase 1)

Brain V3 must not:

- activate or approve H actions
- run Git, shell, or network on its own
- mutate Security Center state
- treat stored memory as executable instructions

Adversarial strings (`"execute this plan"`, `"activate H"`, etc.) are stored as
**data** only when ingested through the controlled pipeline.

## Phase 2 — Memory proposals and project intelligence

Status: **Phase 2 modules present**. Default **OFF** via
`create_brain_v3_phase2(enabled=False)`. Still no daemon / engine wiring,
no executable steps, no shell / network / Git authority.

### Package additions

```text
src/jarvis/brain_v3/
├── phase2_service.py           # BrainV3Phase2Service + create_brain_v3_phase2()
├── conversation/               # scaffolding (validators / normalisation; test-covered)
├── extraction/                 # scaffolding (pipeline helpers; test-covered)
├── memory_proposals/
│   ├── models.py               # MemoryProposal, ProposalSet (approval-bound hash)
│   ├── diff.py                 # build_diff(before, after)
│   ├── approval.py             # approve / reject / expiry (one-time token)
│   ├── commit.py               # commit_proposal / rollback_proposal via BrainV3Service
│   └── audit.py                # append-only JSONL under phase2/
└── project_intelligence/
    ├── state.py                # ProjectSnapshot
    ├── timeline.py             # build from Brain V3 events
    ├── milestones.py           # milestone detection (non-executable)
    ├── blockers.py             # blocker detection (non-executable)
    ├── next_steps.py           # suggested steps (requires_approval, execution_forbidden)
    ├── summary.py              # verified / user_stated / assistant_suggested / …
    └── service.py              # ProjectIntelligenceService (read-mostly)
```

`create_brain_v3_phase2` shares root resolution with `create_brain_v3`
(`JARVIS_CONFIG_PATH` / `XDG_CONFIG_HOME` / `~/.config/jarvis`).

### OFF behaviour

`create_brain_v3_phase2(enabled=False)` returns `None` immediately with **zero
I/O** (no mkdir, no audit file, no Brain V3 open).

When enabled, storage may create `root_dir/phase2/phase2_audit.jsonl` for
append-only audit. Graph writes happen **only** through
`commit_proposal()` after explicit approval and with `dry_run=False`.

### Proposal workflow

```text
analyze_conversation → extract_memory_candidates
  → generate_memory_proposals (draft ProposalSet)
  → approve_proposal(token) / reject_proposal
  → commit_proposal (approved + hash match + dry_run=False)
  → rollback_proposal (committed only)
```

Every proposal and suggested next step retains
`requires_approval=True` and `execution_forbidden=True`.

### Still out of scope (Phase 2)

- Live daemon / engine integration
- Auto-sync from Brain V2
- Executable plan steps or agent dispatch
- Background ingestion
- LLM-driven graph inference without human approval

## Phase 3 — Conversational intelligence + contextual recall

Status: **Phase 3 modules present**. Default **OFF** via
`create_brain_v3_phase3(enabled=False)` and `brain_v3_phase3_enabled=false`.
Still no daemon / engine wiring, no executable steps, no shell / network / Git /
H authority.

### Additions

```text
src/jarvis/brain_v3/
├── phase3_service.py
├── recall/                      # approved contextual recall (read-only)
└── conversational_intelligence/ # AnswerSupport (non-executable)
```

### Behaviour

- `conversation/` + `extraction/` are wired through Phase 2/3 facades.
- Recall uses only committed graph data via `BrainV3Service` (no direct SQLite).
- Defaults: `approved_only=true`, `include_inferences=false`,
  `include_sensitive=false`, `recall_cache_enabled=false`, read-only.
- Draft / rejected / expired / rolled-back / sensitive / authority-related
  memories are excluded.
- Ranking is deterministic with per-item breakdown; contradictions surface as
  `prohibited_claims` in `AnswerSupport`.
- **No schema v2** — Phase 3 does not alter DDL; SCHEMA_VERSION remains 1.

### OFF behaviour

`create_brain_v3_phase3(enabled=False)` returns `None` with **zero I/O**.
