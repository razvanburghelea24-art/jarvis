"""Phase 8.2 — Unified Runtime Snapshot (read-only)."""

from __future__ import annotations

import json

from src.jarvis.cora_foundation.identity import IdentityService
from src.jarvis.cora_foundation.memory import MemoryEngine
from src.jarvis.cora_foundation.planner import PlannerContext, PlannerEngine
from src.jarvis.cora_foundation.snapshot import (
    SnapshotService,
    empty_snapshot,
    reset_snapshot_service_for_tests,
)
from src.jarvis.cora_foundation.snapshot.schema import SCHEMA


def setup_function():
    reset_snapshot_service_for_tests()


def test_empty_snapshot_shape():
    snap = empty_snapshot()
    d = snap.to_dict()
    assert d["schema"] == SCHEMA
    for key in ("runtime", "planner", "scheduler", "agents", "memory", "gateway", "audit", "operator"):
        assert key in d
        assert "health_pct" in d[key]


def test_runtime_live_from_identity(tmp_path):
    identity = IdentityService(enabled=True)
    identity.bootstrap_minimal()
    memory = MemoryEngine(enabled=True, path=tmp_path / "m.json")
    memory.load()
    planner = PlannerEngine(enabled=True)
    planner.create_plan(PlannerContext(request_id="r1", request_text="analyze health"))

    svc = SnapshotService(
        enabled=True,
        path=tmp_path / "snap.json",
        identity=identity,
        memory=memory,
        planner=planner,
    )
    snap = svc.build()
    assert snap.runtime["source"] == "live"
    assert snap.runtime["health_pct"] >= 55
    assert snap.planner["source"] == "live"
    assert snap.memory["record_count"] == 0 or snap.memory["source"] == "live"
    assert snap.operator["indicator"] == "OBSERVE"
    assert snap.operator["controls"] is False

    path = svc.export()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == SCHEMA
    assert set(data.keys()) >= {
        "runtime",
        "planner",
        "scheduler",
        "agents",
        "memory",
        "gateway",
        "audit",
        "operator",
    }
