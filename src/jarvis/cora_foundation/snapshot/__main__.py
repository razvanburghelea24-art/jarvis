"""Dump Unified Snapshot JSON for Electron Host bridge.

Usage:
  python -m jarvis.cora_foundation.snapshot
  python -m jarvis.cora_foundation.snapshot --export PATH
"""

from __future__ import annotations

import argparse
import json
import sys

from .service import SnapshotService, default_snapshot_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Cora Runtime Snapshot (read-only)")
    parser.add_argument("--export", type=str, default="", help="Write JSON to path")
    parser.add_argument("--stdout", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args(argv)

    # Lazy-wire available foundation modules (all may be OFF).
    identity = memory = planner = orchestrator = agents = gateway = audit = operator = estop = None
    try:
        from ..identity import get_identity_service

        identity = get_identity_service()
        if identity.enabled:
            identity.bootstrap_minimal()
    except Exception:
        pass
    try:
        from ..memory import get_memory_engine

        memory = get_memory_engine()
        if memory.enabled:
            memory.load()
    except Exception:
        pass
    try:
        from ..planner import get_planner_engine

        planner = get_planner_engine()
    except Exception:
        pass
    try:
        from ..orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
    except Exception:
        pass
    try:
        from ..agents import get_agent_runtime

        agents = get_agent_runtime()
    except Exception:
        pass
    try:
        from ..gateway import get_command_gateway

        gateway = get_command_gateway()
    except Exception:
        pass
    try:
        from ..audit import get_audit_engine

        audit = get_audit_engine()
    except Exception:
        pass
    try:
        from ..computer_operator import get_computer_operator

        operator = get_computer_operator()
    except Exception:
        pass
    try:
        from ..emergency_stop import get_emergency_stop

        estop = get_emergency_stop()
        if estop.enabled:
            estop.load()
    except Exception:
        pass

    svc = SnapshotService(
        identity=identity,
        memory=memory,
        planner=planner,
        orchestrator=orchestrator,
        agents_runtime=agents,
        gateway=gateway,
        audit=audit,
        operator=operator,
        estop=estop,
    )
    path = args.export or str(default_snapshot_path())
    out = svc.export(path=path)
    if args.stdout:
        print(json.dumps(svc.build().to_dict(), indent=2))
    else:
        print(str(out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
