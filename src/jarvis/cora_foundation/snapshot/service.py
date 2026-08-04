"""SnapshotService — gather read-only sections into one UnifiedSnapshot."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .flags import snapshot_enabled_from_env
from .schema import SCHEMA, UnifiedSnapshot, _now, bar10, empty_snapshot

_SCHEMA_ENGINE = "cora.snapshot.service.v1"


def default_snapshot_path() -> Path:
    import os

    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().parent / "cora_runtime_snapshot.json"
    return Path.home() / ".config" / "jarvis" / "cora_runtime_snapshot.json"


class SnapshotService:
    """
    Read-only aggregator. Does not decide, execute, or write Memory/Policy.
    Optional export to JSON for Electron Host bridge.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        path: Path | str | None = None,
        identity: Any | None = None,
        memory: Any | None = None,
        planner: Any | None = None,
        orchestrator: Any | None = None,
        agents_runtime: Any | None = None,
        gateway: Any | None = None,
        audit: Any | None = None,
        operator: Any | None = None,
        estop: Any | None = None,
    ) -> None:
        self._enabled = snapshot_enabled_from_env() if enabled is None else bool(enabled)
        self._path = Path(path) if path else default_snapshot_path()
        self._identity = identity
        self._memory = memory
        self._planner = planner
        self._orchestrator = orchestrator
        self._agents = agents_runtime
        self._gateway = gateway
        self._audit = audit
        self._operator = operator
        self._estop = estop
        self._lock = threading.RLock()
        self._last: UnifiedSnapshot | None = None
        self._conversation_state: Any | None = None
        self._conversation_events = None  # lazy ConversationEventJournal

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _event_journal(self):
        if self._conversation_events is None:
            from src.jarvis.cora_foundation.conversation.events import (
                get_conversation_event_journal,
            )

            self._conversation_events = get_conversation_event_journal()
        return self._conversation_events

    def set_conversation_state(self, state: Any | None) -> None:
        """Inject ConversationState for Snapshot projection + emit timeline event."""
        from src.jarvis.cora_foundation.conversation.contracts import (
            ConversationState,
            validate_state,
        )

        validated: ConversationState | None
        if state is None:
            validated = None
            presentation = None
            request_id = None
            workspace_id = None
            session_id = None
            lifecycle = None
        else:
            validated = state if isinstance(state, ConversationState) else validate_state(state)
            presentation = validated.presentation.value
            request_id = validated.request_id
            workspace_id = validated.workspace_id
            session_id = validated.session_id
            lifecycle = validated.lifecycle.value

        with self._lock:
            self._conversation_state = validated
        self._event_journal().record_state(
            presentation=presentation if presentation is not None else "Idle",
            request_id=request_id,
            workspace_id=workspace_id,
            session_id=session_id,
            lifecycle=lifecycle,
            force=state is None,
        )

    def clear_conversation_state(self) -> None:
        self.set_conversation_state(None)

    def build(self) -> UnifiedSnapshot:
        if not self._enabled:
            snap = empty_snapshot()
            snap.runtime["detail"] = "snapshot service off"
            return snap

        snap = empty_snapshot()
        snap.generated_at = _now()
        snap.runtime = self._section_runtime()
        snap.planner = self._section_planner()
        snap.scheduler = self._section_scheduler()
        snap.agents = self._section_agents()
        snap.memory = self._section_memory()
        snap.gateway = self._section_gateway()
        snap.audit = self._section_audit()
        snap.operator = self._section_operator()
        snap.conversation = self._section_conversation()
        # Mirror presentation into runtime.status for legacy consumers (Persona prefers conversation).
        if snap.conversation.get("source") == "live" and snap.conversation.get("status"):
            snap.runtime = {
                **snap.runtime,
                "status": snap.conversation["status"],
                "detail": snap.conversation.get("detail") or snap.runtime.get("detail"),
            }
        with self._lock:
            self._last = snap
        return snap

    def export(self, *, path: Path | str | None = None) -> Path:
        """Write snapshot JSON for Electron Host (read-only bridge file)."""
        target = Path(path) if path else self._path
        snap = self.build()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
        return target

    def last(self) -> UnifiedSnapshot | None:
        return self._last

    # ── sections ─────────────────────────────────────────────────────────

    def _section_runtime(self) -> dict[str, Any]:
        who: dict[str, Any] = {}
        enabled = False
        try:
            if self._identity is not None:
                enabled = bool(getattr(self._identity, "enabled", False))
                snap = self._identity.snapshot()
                who = snap.to_public_dict() if hasattr(snap, "to_public_dict") else {}
        except Exception as exc:  # noqa: BLE001 — snapshot must not crash
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 40.0,
                "detail": f"identity error: {exc}",
                "status": "Idle",
                "bar": bar10(40),
            }

        estop = False
        safe = False
        state = "Idle"
        if isinstance(who.get("who_are_you"), dict):
            runtime = who["who_are_you"]
            state = str(runtime.get("current_state") or "Idle")
            safe = bool(runtime.get("safe_mode"))
            estop = bool(runtime.get("e_stop"))

        if self._estop is not None and getattr(self._estop, "enabled", False):
            try:
                from ..emergency_stop.states import is_estop_mode

                mode = self._estop.current_mode()
                estop = is_estop_mode(mode)
                if estop:
                    state = "E-Stop"
                elif str(mode.value).lower() == "safe_mode":
                    safe = True
                    state = "Safe Mode"
            except Exception:
                pass

        pct = 100.0 if enabled else 55.0
        if estop:
            pct = 15.0
        elif safe:
            pct = 50.0

        return {
            "source": "live" if enabled else "bridge_stub",
            "health": "on" if enabled and not estop else ("degraded" if enabled else "off"),
            "health_pct": pct,
            "detail": "Identity → Runtime",
            "status": state,
            "bar": bar10(pct),
            "identity_enabled": enabled,
            "who": who.get("who"),
            "session": who.get("active_session"),
            "workspace": who.get("where"),
            "runtime": who.get("who_are_you"),
            "safe_mode": safe,
            "e_stop": estop,
            "schema": SCHEMA,
        }

    def _section_planner(self) -> dict[str, Any]:
        eng = self._planner
        if eng is None:
            return self._pending("planner", "Idle")
        enabled = bool(getattr(eng, "enabled", False))
        status = "Idle"
        plan_count = 0
        try:
            st = eng.status() if hasattr(eng, "status") else {}
            plan_count = int(st.get("plan_count") or 0)
            if enabled and plan_count:
                status = "Planning"
            plans = eng.list_plans() if hasattr(eng, "list_plans") else []
            if plans:
                last = plans[-1]
                status = getattr(getattr(last, "status", None), "value", None) or str(
                    getattr(last, "status", "Idle")
                )
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 35.0,
                "detail": str(exc),
                "status": "Idle",
                "bar": bar10(35),
            }
        pct = 100.0 if enabled else 0.0
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "plan-only",
            "status": status if enabled else "Idle",
            "plan_count": plan_count,
            "executes": False,
            "bar": bar10(pct),
        }

    def _section_scheduler(self) -> dict[str, Any]:
        orch = self._orchestrator
        if orch is None:
            return self._pending("scheduler", "Idle")
        enabled = bool(getattr(orch, "enabled", False))
        graph = orch.graph() if hasattr(orch, "graph") else None
        bars: list[dict[str, Any]] = []
        ready = 0
        try:
            if graph is not None and hasattr(orch, "progress"):
                prog = orch.progress()
                if prog is not None:
                    ready = int(prog.parallel_ready)
                    for row in prog.bars:
                        bars.append(
                            {
                                "task_id": row.get("task_id"),
                                "label": row.get("label"),
                                "status": row.get("status"),
                                "fill": row.get("fill"),
                                "bar": row.get("bar"),
                            }
                        )
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 35.0,
                "detail": str(exc),
                "status": "Idle",
                "task_bars": [],
                "bar": bar10(35),
            }
        pct = 100.0 if enabled else 0.0
        status = "Running" if ready else ("Idle" if not bars else "Waiting")
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "TaskGraph waves",
            "status": status if enabled else "Idle",
            "task_bars": bars,
            "parallel_ready": ready,
            "bar": bar10(pct),
        }

    def _section_agents(self) -> dict[str, Any]:
        rt = self._agents
        if rt is None:
            return self._pending("agents", "Idle")
        enabled = bool(getattr(rt, "enabled", False))
        roles: list[str] = []
        try:
            st = rt.status() if hasattr(rt, "status") else {}
            roles = list(st.get("roles") or [])
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 35.0,
                "detail": str(exc),
                "status": "Idle",
                "bar": bar10(35),
            }
        pct = 100.0 if enabled else 0.0
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "specialists",
            "status": "Ready" if enabled else "Idle",
            "roles": roles,
            "dispatches": False,
            "bar": bar10(pct),
        }

    def _section_memory(self) -> dict[str, Any]:
        mem = self._memory
        if mem is None:
            return self._pending("memory", "Idle")
        enabled = bool(getattr(mem, "enabled", False))
        try:
            snap = mem.snapshot() if hasattr(mem, "snapshot") else {}
            count = int(snap.get("record_count") or 0)
            revision = snap.get("revision")
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 35.0,
                "detail": str(exc),
                "status": "Idle",
                "bar": bar10(35),
            }
        pct = 100.0 if enabled else 0.0
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "SSOT read-only view",
            "status": "Ready" if enabled else "Idle",
            "record_count": count,
            "revision": revision,
            "writes_from_ui": False,
            "bar": bar10(pct),
        }

    def _section_gateway(self) -> dict[str, Any]:
        gw = self._gateway
        if gw is None:
            return self._pending("gateway", "Idle")
        enabled = bool(getattr(gw, "enabled", False))
        pct = 100.0 if enabled else 0.0
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "single entry",
            "status": "Ready" if enabled else "Idle",
            "request_count": 0,
            "pipeline": "normalize→identity→memory→intent→policy→plan→dispatch",
            "latency_ms": None,
            "bar": bar10(pct),
        }

    def _section_audit(self) -> dict[str, Any]:
        audit = self._audit
        if audit is None:
            return self._pending("audit", "Idle")
        enabled = bool(getattr(audit, "enabled", False))
        events = 0
        timeline: list[dict[str, Any]] = []
        try:
            if enabled and hasattr(audit, "read_all"):
                all_ev = list(audit.read_all())[-12:]
                events = len(all_ev)
                for ev in all_ev:
                    timeline.append(
                        {
                            "type": getattr(ev.event_type, "value", str(ev.event_type)),
                            "status": ev.status,
                            "request_id": ev.request_id,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "bridge_stub",
                "health": "degraded",
                "health_pct": 35.0,
                "detail": str(exc),
                "status": "Idle",
                "timeline": [],
                "bar": bar10(35),
            }
        pct = 100.0 if enabled else 0.0
        return {
            "source": "live" if enabled else "off",
            "health": "on" if enabled else "off",
            "health_pct": pct,
            "detail": "append-only",
            "status": "Ready" if enabled else "Idle",
            "event_count": events,
            "timeline": timeline,
            "bar": bar10(pct),
        }

    def _section_operator(self) -> dict[str, Any]:
        op = self._operator
        indicator = "OBSERVE"
        enabled = False
        if op is not None:
            enabled = bool(getattr(op, "enabled", False))
            try:
                ind = op.indicator() if hasattr(op, "indicator") else None
                if ind is not None:
                    indicator = getattr(ind, "value", str(ind))
            except Exception:
                pass
        # Phase 6A: always surface OBSERVE for UI even if module off
        pct = 99.0 if enabled else 70.0
        return {
            "source": "live" if enabled else "bridge_stub",
            "health": "on",
            "health_pct": pct,
            "detail": "OBSERVE only · 6B off",
            "status": indicator,
            "indicator": "OBSERVE" if indicator == "OBSERVE" or not enabled else indicator,
            "controls": False,
            "bar": bar10(pct),
        }

    def _section_conversation(self) -> dict[str, Any]:
        from src.jarvis.cora_foundation.conversation.projection import (
            empty_conversation_section,
            project_conversation_state,
        )

        with self._lock:
            state = self._conversation_state
        if state is None:
            section = empty_conversation_section()
        else:
            try:
                section = project_conversation_state(state)
            except Exception as exc:  # noqa: BLE001 — snapshot must not crash
                section = empty_conversation_section()
                section["source"] = "bridge_stub"
                section["health"] = "degraded"
                section["detail"] = f"conversation projection error: {exc}"
        section["events"] = self._event_journal().to_timeline(limit=40)
        return section

    def _pending(self, name: str, status: str) -> dict[str, Any]:
        return {
            "source": "bridge_stub",
            "health": "off",
            "health_pct": 0.0,
            "detail": f"{name} not wired",
            "status": status,
            "bar": bar10(0),
        }


_SVC: SnapshotService | None = None
_LOCK = threading.Lock()


def get_snapshot_service(**kwargs: Any) -> SnapshotService:
    global _SVC
    with _LOCK:
        if _SVC is None:
            _SVC = SnapshotService(**kwargs)
        return _SVC


def reset_snapshot_service_for_tests() -> None:
    global _SVC
    with _LOCK:
        _SVC = None
