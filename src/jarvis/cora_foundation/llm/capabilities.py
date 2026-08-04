"""ModelCapability — router sees capabilities, not vendor names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelCapability:
    """Scores/flags for capability-based routing (not vendor names)."""

    reasoning: int = 5
    coding: int = 5
    creativity: int = 5
    speed: int = 5
    vision: int = 0
    context_window: int = 8  # relative 0–10 (not raw tokens)
    offline: bool = False
    streaming: bool = False
    tool_calling: bool = False
    cost: int = 5  # 0 free … 10 expensive (alias cost_per_1k_tokens scale)
    cost_per_1k_tokens: float = 0.0
    availability: bool = True
    provider_id: str = ""
    model_id: str = ""

    def __post_init__(self) -> None:
        for name in (
            "reasoning",
            "coding",
            "creativity",
            "speed",
            "vision",
            "context_window",
            "cost",
        ):
            val = int(getattr(self, name))
            object.__setattr__(self, name, max(0, min(10, val)))
        object.__setattr__(self, "cost_per_1k_tokens", float(self.cost_per_1k_tokens))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning": self.reasoning,
            "coding": self.coding,
            "creativity": self.creativity,
            "speed": self.speed,
            "vision": self.vision,
            "context_window": self.context_window,
            "offline": self.offline,
            "streaming": self.streaming,
            "tool_calling": self.tool_calling,
            "cost": self.cost,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "availability": self.availability,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


def _cap(**kwargs: Any) -> ModelCapability:
    return ModelCapability(**kwargs)


CAPABILITY_MOCK = _cap(
    reasoning=1,
    coding=1,
    creativity=1,
    speed=10,
    vision=0,
    context_window=2,
    offline=True,
    streaming=False,
    tool_calling=False,
    cost=0,
    cost_per_1k_tokens=0.0,
    availability=True,
    provider_id="mock",
    model_id="mock-v1",
)

CAPABILITY_OLLAMA_DEFAULT = _cap(
    reasoning=6,
    coding=6,
    creativity=5,
    speed=7,
    vision=0,
    context_window=5,
    offline=True,
    streaming=True,
    tool_calling=False,
    cost=0,
    cost_per_1k_tokens=0.0,
    availability=True,
    provider_id="ollama",
    model_id="llama3.2",
)

CAPABILITY_OPENAI_DEFAULT = _cap(
    reasoning=8,
    coding=8,
    creativity=8,
    speed=7,
    vision=0,
    context_window=8,
    offline=False,
    streaming=True,
    tool_calling=False,
    cost=7,
    cost_per_1k_tokens=0.005,
    availability=True,
    provider_id="openai",
    model_id="gpt-4o-mini",
)

CAPABILITY_CLAUDE_DEFAULT = _cap(
    reasoning=9,
    coding=9,
    creativity=7,
    speed=6,
    vision=0,
    context_window=9,
    offline=False,
    streaming=True,
    tool_calling=False,
    cost=8,
    cost_per_1k_tokens=0.008,
    availability=True,
    provider_id="claude",
    model_id="claude-sonnet-4-20250514",
)
