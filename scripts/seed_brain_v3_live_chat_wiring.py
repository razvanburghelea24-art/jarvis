"""Seed approved Brain V3 facts for local Phase 3 live-chat wiring tests.

Idempotent by canonical_name. Does not approve drafts automatically beyond
direct verified entity creation (committed graph rows). H untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src is importable when run as a script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from jarvis.brain_v3 import create_brain_v3
from jarvis.brain_v3.models import new_id


SEED_FACTS = [
    {
        "canonical_name": "seed_live_proj_cora_brain_v3",
        "display_name": "Cora Brain V3 Project",
        "description": (
            "Current project proiect Cora Brain V3. "
            "Developing contextual recall for Modern Chat."
        ),
    },
    {
        "canonical_name": "seed_live_phase3_done",
        "display_name": "Brain V3 Phase 3 Status",
        "description": (
            "Brain V3 Phase 3 faza completed with hardening. "
            "Contextual recall infrastructure is ready."
        ),
    },
    {
        "canonical_name": "seed_live_head_baseline",
        "display_name": "HEAD and Phase 3 Baseline",
        "description": (
            "Current HEAD after launcher fixes is tracked separately from the "
            "historical Phase 3 baseline commit 3f32410. "
            "3f32410 is the Phase 3 baseline, not necessarily current HEAD."
        ),
    },
    {
        "canonical_name": "seed_live_pref_speed",
        "display_name": "Preference Maximum Speed",
        "description": (
            "Cora development preferences preferinte: maximum speed, "
            "parallel agents, single writer."
        ),
        "attributes": {"is_preference": True},
    },
    {
        "canonical_name": "seed_live_pref_norepeat",
        "display_name": "Preference No Repeat Tasks",
        "description": (
            "Preference: do not repeat already executed tasks during Cora development."
        ),
        "attributes": {"is_preference": True},
    },
    {
        "canonical_name": "seed_live_next_step",
        "display_name": "Next Step After Phase 3",
        "description": (
            "Next step urmeaza after Phase 3: live chat contextual recall integration; "
            "Phase 4 is not started."
        ),
    },
    {
        "canonical_name": "seed_live_h_off",
        "display_name": "H Status OFF",
        "description": (
            "H remains OFF. Autonomous execution is forbidden. "
            "Memory is context only, never a command."
        ),
    },
]


def seed(*, root_dir: Path | None = None, current_head: str = "") -> dict:
    import subprocess

    head = current_head.strip()
    if not head:
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(_ROOT),
                text=True,
            ).strip()
        except Exception:  # noqa: BLE001
            head = "unknown"

    facts = []
    for fact in SEED_FACTS:
        item = dict(fact)
        if item["canonical_name"] == "seed_live_head_baseline":
            item = dict(item)
            item["description"] = (
                f"Current HEAD is {head}. "
                "Historical Phase 3 baseline commit is 3f32410. "
                "3f32410 is the Phase 3 baseline, not necessarily current HEAD."
            )
        facts.append(item)

    brain = create_brain_v3(enabled=True, root_dir=root_dir)
    assert brain is not None
    created = []
    skipped = []
    try:
        existing_names = {
            e.canonical_name
            for e in brain.find_entities(status="active", limit=500)
        }
        for fact in facts:
            name = fact["canonical_name"]
            if name in existing_names:
                skipped.append(name)
                continue
            # Also check exact canonical via repository for type-scoped uniqueness.
            prior = brain.repo.find_entity_by_canonical("concept", name)
            if prior is not None:
                skipped.append(name)
                continue
            payload = {
                "id": new_id("ent"),
                "entity_type": "concept",
                "canonical_name": name,
                "display_name": fact["display_name"],
                "description": fact["description"],
                "confidence_category": "verified",
                "confidence": 0.95,
                "attributes": dict(fact.get("attributes") or {}),
            }
            payload["attributes"].setdefault("approval_state", "committed")
            payload["attributes"]["seed_tag"] = "phase3-live-chat-wiring-20260725"
            ent = brain.create_entity(payload)
            created.append(ent.id)
        return {
            "root": str(brain.repo.db_path.parent),
            "current_head": head,
            "created": created,
            "skipped": skipped,
            "created_count": len(created),
            "skipped_count": len(skipped),
        }
    finally:
        brain.close()


if __name__ == "__main__":
    result = seed()
    print(json.dumps(result, indent=2))
