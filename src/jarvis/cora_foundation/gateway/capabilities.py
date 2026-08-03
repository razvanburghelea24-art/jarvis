"""Capability Registry — names only; no implementations of external APIs."""

from __future__ import annotations

from dataclasses import dataclass

from .types import RiskLevel


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    risk_level: RiskLevel
    description: str = ""


# Canonical capability names (Gateway works with these, not raw APIs).
DEFAULT_CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("OwnerProfile.read", RiskLevel.READ, "Read owner profile memory"),
    CapabilitySpec("OwnerProfile.write", RiskLevel.OWNER_CONFIRM, "Write owner profile memory"),
    CapabilitySpec("Workspace.scan", RiskLevel.READ, "Scan workspace metadata"),
    CapabilitySpec("Discord.send", RiskLevel.OWNER_CONFIRM, "Send Discord message via bot connector"),
    CapabilitySpec("Overlay.refresh", RiskLevel.SAFE_LOCAL, "Refresh overlay panel"),
    CapabilitySpec("GitHub.create_pr", RiskLevel.CRITICAL, "Create GitHub pull request"),
    CapabilitySpec("Railway.deploy", RiskLevel.CRITICAL, "Trigger Railway deploy"),
    CapabilitySpec("Server.restart", RiskLevel.CRITICAL, "Request game/server restart"),
    CapabilitySpec("Memory.read", RiskLevel.READ, "Read Memory SSOT"),
    CapabilitySpec("Memory.write", RiskLevel.OWNER_CONFIRM, "Write Memory SSOT"),
    CapabilitySpec("Identity.whoami", RiskLevel.READ, "Identity snapshot"),
    CapabilitySpec("Computer.observe", RiskLevel.READ, "Desktop observability (no control)"),
    CapabilitySpec("Computer.click", RiskLevel.CRITICAL, "Mouse click (6B assisted)"),
    CapabilitySpec("Computer.type_keys", RiskLevel.CRITICAL, "Keyboard injection (6B assisted)"),
    CapabilitySpec("Computer.move_mouse", RiskLevel.CRITICAL, "Mouse move (6B assisted)"),
    CapabilitySpec("Computer.open_app", RiskLevel.CRITICAL, "Open application (6B assisted)"),
    CapabilitySpec("Computer.close_app", RiskLevel.CRITICAL, "Close application (6B assisted)"),
    CapabilitySpec("Computer.write_clipboard", RiskLevel.OWNER_CONFIRM, "Clipboard write (6B)"),
    CapabilitySpec("Computer.execute_preview", RiskLevel.CRITICAL, "Execute approved Action Preview (6B)"),
)


class CapabilityRegistry:
    def __init__(self, specs: tuple[CapabilitySpec, ...] | list[CapabilitySpec] | None = None) -> None:
        items = tuple(specs) if specs is not None else DEFAULT_CAPABILITIES
        self._by_name = {s.name: s for s in items}

    def get(self, name: str) -> CapabilitySpec | None:
        return self._by_name.get(name)

    def has(self, name: str) -> bool:
        return name in self._by_name

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))

    def risk_for(self, name: str) -> RiskLevel:
        spec = self.get(name)
        return RiskLevel.FORBIDDEN if spec is None else spec.risk_level


def default_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry()
