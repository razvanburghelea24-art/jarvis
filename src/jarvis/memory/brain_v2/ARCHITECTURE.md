# Brain Memory v2 — Architecture (internal)

Status: **Preference + Project vertical slice** (durable JSON). Other five
modules remain in-memory stubs. Default-OFF. Not wired into `reply.engine`,
daemon, audio, Security Center, or internet research.

## Why

Today memory is spread across:

| Existing | Role today |
|----------|------------|
| `DialogueMemory` | Hot conversation window (RAM) |
| Diary / `conversation_summaries` | Session summaries |
| `GraphMemoryStore` | Knowledge nodes |
| `LearningStore` | Lessons from conversations |
| `StateStore` | Confirmed facts with audit (SQLite) |
| `OwnerProfile` | Authoritative owner JSON |
| `ConversationStore` | UI chat transcripts |
| Identity / local answers | Deterministic short-circuits |

Brain Memory v2 introduces **seven named modules** so future work can
migrate responsibilities without a big-bang rewrite. This slice adds a
**separate** on-disk store for Preference + Project only — it does **not**
read or write StateStore / Owner Profile / learning tables.

## What is reused (not duplicated blindly)

| Building block | Reuse |
|----------------|-------|
| `jarvis.utils.atomic_write` | Crash-safe overwrite + sibling `.bak` |
| Owner Profile fail-safe load pattern | Corrupt → empty, never raise |
| `jarvis.utils.redact.scrub_secrets` | Log redaction only |
| StateStore *concepts* | propose ≠ confirm; confirmed = authoritative |
| Config dir resolution | `~/.config/jarvis` / `JARVIS_CONFIG_PATH` |

**Not reused as backend:** StateStore SQLite, Owner Profile file, Security
Center `atomic_io`, learning lessons DB.

## Module map

```
                    ┌─────────────────────┐
                    │   BrainMemoryV2     │
                    │      (facade)       │
                    └──────────┬──────────┘
       ┌───────────┬───────────┼───────────┬───────────┬───────────┐
       ▼           ▼           ▼           ▼           ▼           ▼
   ShortTerm   LongTerm    Episodic    Semantic     Skill    Preference*
                                                              + Project*
   (stub)      (stub)      (stub)      (stub)      (stub)   (* durable JSON)
```

### Data flow (Preference / Project)

```
caller (future UI / tools — NOT engine yet)
    │
    ▼
PreferenceMemory / ProjectMemory  ──API──►  BrainV2JsonStore
                                              │
                                              ├─ preferences.json | projects.json
                                              ├─ *.bak (atomic_write)
                                              └─ backups/<stem>-<utc>.json
```

Flag OFF → `create_brain_memory_v2()` returns `None` → **zero I/O**.

### 1. Short-Term Memory (`stm`) — stub

| | |
|--|--|
| **Responsibility** | Current conversation turns. |
| **Persistence** | RAM only (this slice). |

### 2. Long-Term Memory (`ltm`) — stub

| | |
|--|--|
| **Responsibility** | Durable owner/world facts. |
| **Persistence** | RAM only; future StateStore bridge. |

### 3. Episodic Memory (`episodic`) — stub

Session summaries. RAM only.

### 4. Semantic Memory (`semantic`) — stub

Concepts + links. RAM only.

### 5. Skill Memory (`skill`) — stub

Procedural notes. **Reading never grants execution.** No skill runner in v2.

### 6. Preference Memory (`preference`) — **durable**

| | |
|--|--|
| **Responsibility** | Owner preferences with explicit confirmation. |
| **Data** | `PreferenceMemoryRecord` (`key`, `value`, `confidence`, `source`, `confirmed`, timestamps, `schema_version`) |
| **API** | `get`, `list`, `propose`, `confirm`, `reject`, `delete` |
| **Authority** | Only `confirmed=True` may later be treated as authoritative by consumers. |
| **Confirmation policy** | `propose` always sets `confirmed=False`. No auto-confirm. No auto-learning. |
| **Limits** | Safe keys only (`[A-Za-z0-9._-]`); no path traversal; values clamped. |
| **Persistence** | `preferences.json` under brain_v2 root |
| **Retention** | Explicit `reject`/`delete` removes the key; no TTL in this slice. |

### 7. Project Memory (`project`) — **durable**

| | |
|--|--|
| **Responsibility** | Active project id and project facts / next steps. |
| **Data** | `ProjectMemoryRecord` (`project_id`, `name`, `status`, `summary`, `active_goal`, `last_action`, `next_action`, `metadata`, timestamps, `schema_version`) |
| **API** | `create`, `get`, `list`, `set_active`, `update_status`, `update_next_action`, `archive` |
| **Authority** | Informational project state only — **never executes** `next_action`. |
| **Limits** | One `active_project_id` pointer; archived projects cannot be set active. |
| **Persistence** | `projects.json` + `active_project_id` field |
| **Retention** | `archive` sets status; record kept until future retention policy. |

## On-disk layout (runtime only — not in Git)

```
~/.config/jarvis/memory/brain_v2/
  preferences.json
  projects.json
  backups/
    preferences-YYYYMMDDThhmmssZ.json
    projects-YYYYMMDDThhmmssZ.json
```

Timestamped backups are **bounded** (default keep 10 per store stem).
Sibling `*.bak` comes from `atomic_write` (single slot).

Override root via `create_brain_memory_v2(..., root_dir=...)`.
`JARVIS_CONFIG_PATH` relocates the config dir (and thus the default root).

## Feature flag

`brain_memory_v2_enabled` (default **`false`**).

| Flag | Behaviour |
|------|-----------|
| OFF | Factory → `None`; no mkdir; no JSON |
| ON | Opens Preference/Project stores; corrupt → recover/empty; storage errors → memory-only facade (`storage_ok=False`), no daemon crash |

## Difference vs existing memory

| Concern | Existing | Brain Memory v2 (this slice) |
|---------|----------|------------------------------|
| Preferences | StateStore `user_preference` (+ audit) | Separate JSON, confirm gate, no SQLite |
| Project facts | StateStore `project_fact` / lessons | Separate `projects.json` |
| Owner identity | Owner Profile JSON | Unchanged; not mirrored here |
| Conversation | DialogueMemory / ConversationStore | Unchanged (STM stub only) |

No migration and no deletion of existing stores in this slice.

## Future migration plan (not implemented)

1. Optional read-through adapters: StateStore confirmed prefs → PreferenceMemory candidates.
2. Dual-write behind a second flag.
3. Cut over consumers (still not engine until an explicit wiring PR).
4. Never drop StateStore rows automatically.

## Non-goals (this slice)

* No DDL / SQLite for brain_v2
* No engine or daemon imports on the hot path
* No Security Center / audio / `internet_research` changes
* No skill execution, no auto-learning, no secret persistence in logs
