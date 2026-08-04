"""Timing metrics for the live execution chain (ms)."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class ChainMetrics:
    conversation_ms: float = 0.0
    planner_ms: float = 0.0
    tool_routing_ms: float = 0.0
    dispatcher_ms: float = 0.0
    gateway_ms: float = 0.0
    github_ms: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def total_ms(self) -> float:
        return (
            self.conversation_ms
            + self.planner_ms
            + self.tool_routing_ms
            + self.dispatcher_ms
            + self.gateway_ms
            + self.github_ms
            + sum(self.extra.values())
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_engine_ms": round(self.conversation_ms, 3),
            "planner_ms": round(self.planner_ms, 3),
            "tool_routing_ms": round(self.tool_routing_ms, 3),
            "dispatcher_ms": round(self.dispatcher_ms, 3),
            "gateway_ms": round(self.gateway_ms, 3),
            "github_ms": round(self.github_ms, 3),
            "extra_ms": {k: round(v, 3) for k, v in self.extra.items()},
            "total_ms": round(self.total_ms, 3),
        }

    def panel_lines(self) -> list[str]:
        d = self.to_dict()
        return [
            f"Conversation Engine: {d['conversation_engine_ms']} ms",
            f"Planner: {d['planner_ms']} ms",
            f"Tool Routing: {d['tool_routing_ms']} ms",
            f"Dispatcher: {d['dispatcher_ms']} ms",
            f"Gateway: {d['gateway_ms']} ms",
            f"GitHub: {d['github_ms']} ms",
            f"TOTAL: {d['total_ms']} ms",
        ]


class Timer:
    def __init__(self) -> None:
        self._t0 = perf_counter()

    def ms(self) -> float:
        return (perf_counter() - self._t0) * 1000.0
