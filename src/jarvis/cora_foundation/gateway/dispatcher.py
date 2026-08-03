"""Capability Dispatcher — sole path to capability handlers.

Order: Capability lookup → E-Stop gate → (Policy already decided) → handler.
Handlers are stubs — no live Discord/GitHub/Railway/Overlay calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..emergency_stop import EmergencyStopEngine
from .capabilities import CapabilityRegistry
from .types import ExecutionPlan, Intent


@dataclass(frozen=True)
class DispatchResult:
    ok: bool
    capability: str
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class CapabilityHandler(Protocol):
    def __call__(self, intent: Intent, plan: ExecutionPlan) -> DispatchResult: ...


def _stub(capability: str) -> CapabilityHandler:
    def _handler(intent: Intent, plan: ExecutionPlan) -> DispatchResult:
        return DispatchResult(
            ok=True,
            capability=capability,
            result={
                "stub": True,
                "capability": capability,
                "intent_type": intent.type,
                "message": "capability acknowledged (no live side effects)",
            },
        )

    return _handler


class CapabilityDispatcher:
    def __init__(
        self,
        registry: CapabilityRegistry,
        handlers: dict[str, CapabilityHandler] | None = None,
        emergency_stop: EmergencyStopEngine | None = None,
    ) -> None:
        self._registry = registry
        self._handlers: dict[str, CapabilityHandler] = dict(handlers or {})
        self._estop = emergency_stop
        for name in registry.names():
            self._handlers.setdefault(name, _stub(name))

    def bind_emergency_stop(self, engine: EmergencyStopEngine | None) -> None:
        self._estop = engine

    def register(self, capability: str, handler: CapabilityHandler) -> None:
        if not self._registry.has(capability):
            raise KeyError(f"unknown capability: {capability}")
        self._handlers[capability] = handler

    def dispatch(self, intent: Intent, plan: ExecutionPlan) -> list[DispatchResult]:
        results: list[DispatchResult] = []
        for cap in plan.capabilities:
            if not self._registry.has(cap):
                results.append(
                    DispatchResult(ok=False, capability=cap, error="capability not registered")
                )
                continue
            # Hard gate: E-Stop / Safe Mode cannot be bypassed by handlers.
            if self._estop is not None and not self._estop.allows_capability(cap):
                snap = self._estop.snapshot()
                results.append(
                    DispatchResult(
                        ok=False,
                        capability=cap,
                        error=f"blocked by safety mode {snap.get('mode')}",
                        result={
                            "blocked": True,
                            "safety": snap,
                            "message": snap.get("message"),
                        },
                    )
                )
                continue
            handler = self._handlers.get(cap) or _stub(cap)
            results.append(handler(intent, plan))
        return results
