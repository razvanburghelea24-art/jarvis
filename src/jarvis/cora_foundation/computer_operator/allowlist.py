"""Configurable application allowlist — deny by default outside list."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_ALLOWLIST: tuple[str, ...] = (
    "VS Code",
    "Code",
    "Blender",
    "Unreal",
    "UnrealEditor",
    "Explorer",
    "Chrome",
    "Discord",
)


@dataclass
class AppAllowlist:
    """Apps Operator may observe deeply / (later) control. Others = DENY."""

    allowed: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWLIST))

    def is_allowed(self, app_name: str | None) -> bool:
        if not app_name:
            return False
        name = app_name.strip().lower()
        return any(name == a.lower() or name.startswith(a.lower()) for a in self.allowed)

    def deny_reason(self, app_name: str | None) -> str | None:
        if self.is_allowed(app_name):
            return None
        return f"DENY: app not on allowlist ({app_name!r})"

    def to_public_dict(self) -> dict:
        return {"allowed": sorted(self.allowed), "default_policy": "DENY"}
