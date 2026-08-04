"""ModelCapability — router sees capabilities, not vendor names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelCapability:
    """Scores 0–10. Router matches needs → capabilities (Stage 3)."""

    reasoning: int = 5
    coding: int = 5
    vision: int = 0
    speed: int = 5
    offline: bool = False
    streaming: bool = False
    tool_calling: bool = False
    cost: int = 5  # lower = cheaper (0 free … 10 expensive)
    provider_id: str = ""
    model_id: str = ""

    def __post_init__(self) -> None:
        for name in ("reasoning", "coding", "vision", "speed", "cost"):
            val = int(getattr(self, name))
            object.__setattr__(self, name, max(0, min(10, val)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning": self.reasoning,
            "coding": self.coding,
            "vision": self.vision,
            "speed": self.speed,
            "offline": self.offline,
            "streaming": self.streaming,
            "tool_calling": self.tool_calling,
            "cost": self.cost,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


# Default capability profiles (Stage 2 registry seeds — Router consumes later)
CAPABILITY_MOCK = ModelCapability(
    reasoning=1,
    coding=1,
    vision=0,
    speed=10,
    offline=True,
    streaming=False,
    tool_calling=False,
    cost=0,
    provider_id="mock",
    model_id="mock-v1",
)

CAPABILITY_OLLAMA_DEFAULT = ModelCapability(
    reasoning=6,
    coding=6,
    vision=0,
    speed=7,
    offline=True,
    streaming=True,
    tool_calling=False,
    cost=0,
    provider_id="ollama",
    model_id="llama3.2",
)
