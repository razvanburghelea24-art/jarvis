"""Command Gateway — the single entry point for all commands."""

from __future__ import annotations

import threading
from pathlib import Path

from ..identity import IdentityService, get_identity_service
from ..memory import MemoryEngine, get_memory_engine
from .audit_hooks import AuditJournal
from .capabilities import CapabilityRegistry, default_capability_registry
from .dispatcher import CapabilityDispatcher
from .flags import gateway_enabled_from_env
from .intent import IntentEngine
from .pipeline import CommandPipeline, PipelineResult
from .policy import PolicyEngine
from .types import CommandEnvelope, SourceChannel


class CommandGateway:
    """Single command entry. Does not execute business APIs — dispatches capabilities only."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        identity: IdentityService | None = None,
        memory: MemoryEngine | None = None,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self._enabled = gateway_enabled_from_env() if enabled is None else bool(enabled)
        self._identity = identity
        self._memory = memory
        self._registry = registry or default_capability_registry()
        self._dispatcher = CapabilityDispatcher(self._registry)
        self._audit = AuditJournal()
        self._pipeline = CommandPipeline(
            intent_engine=IntentEngine(),
            policy_engine=PolicyEngine(),
            registry=self._registry,
            dispatcher=self._dispatcher,
            audit=self._audit,
            identity=self._identity,
            memory=self._memory,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    @property
    def audit(self) -> AuditJournal:
        return self._audit

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def submit(
        self,
        text: str,
        *,
        source: SourceChannel | str = SourceChannel.UNKNOWN,
        metadata: dict | None = None,
    ) -> PipelineResult:
        if isinstance(source, str):
            try:
                source = SourceChannel(source)
            except ValueError:
                source = SourceChannel.UNKNOWN
        envelope = CommandEnvelope(text=text, source=source, metadata=dict(metadata or {}))
        return self._pipeline.run(envelope, enabled=self._enabled)


_GW: CommandGateway | None = None
_GW_LOCK = threading.Lock()


def get_command_gateway(
    *,
    enabled: bool | None = None,
    memory_path: Path | str | None = None,
) -> CommandGateway:
    """Process singleton. Wires Identity + Memory services when present (consume, don't clone)."""
    global _GW
    with _GW_LOCK:
        if _GW is None:
            identity = get_identity_service()
            memory = get_memory_engine(path=memory_path) if memory_path is not None else get_memory_engine()
            _GW = CommandGateway(enabled=enabled, identity=identity, memory=memory)
        elif enabled is not None:
            _GW.set_enabled(bool(enabled))
        return _GW


def reset_command_gateway_for_tests() -> None:
    global _GW
    with _GW_LOCK:
        _GW = None
