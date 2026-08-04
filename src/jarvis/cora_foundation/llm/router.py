"""ModelRouter — capability-based provider selection (not vendor ifs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .adapter import LLMAdapter
from .capabilities import ModelCapability
from .contracts import LLMRequest, LLMResponse
from .registry import ProviderEntry, ProviderRegistry


@dataclass(frozen=True)
class RouteNeeds:
    """What this turn needs. Router matches Needs → ModelCapability."""

    reasoning: int = 0
    coding: int = 0
    creativity: int = 0
    speed: int = 0
    vision: int = 0
    context_window: int = 0
    require_offline: bool = False
    require_streaming: bool = False
    require_tool_calling: bool = False
    max_cost: int | None = None  # prefer cost <= max_cost when set

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> RouteNeeds:
        data = data or {}
        return cls(
            reasoning=int(data.get("reasoning") or 0),
            coding=int(data.get("coding") or 0),
            creativity=int(data.get("creativity") or 0),
            speed=int(data.get("speed") or 0),
            vision=int(data.get("vision") or 0),
            context_window=int(data.get("context_window") or 0),
            require_offline=bool(data.get("require_offline") or data.get("offline") or False),
            require_streaming=bool(data.get("require_streaming") or False),
            require_tool_calling=bool(data.get("require_tool_calling") or False),
            max_cost=int(data["max_cost"]) if data.get("max_cost") is not None else None,
        )


@dataclass(frozen=True)
class RouteDecision:
    provider_id: str
    model_id: str
    score: float
    capability: ModelCapability
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "score": self.score,
            "reason": self.reason,
            "capability": self.capability.to_dict(),
        }


class ModelRouter:
    """
    ConversationContext / Needs → best ProviderEntry → LLMAdapter.

    Never branches on vendor names in callers — only on capabilities.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def resolve(self, needs: RouteNeeds | Mapping[str, Any] | None = None) -> RouteDecision:
        req = needs if isinstance(needs, RouteNeeds) else RouteNeeds.from_mapping(needs)
        candidates: list[tuple[float, ProviderEntry, str]] = []
        for entry in self.registry.entries():
            cap = entry.capability
            ok, why_not = self._eligible(cap, req)
            if not ok:
                continue
            score, reason = self._score(cap, req)
            candidates.append((score, entry, reason))
        if not candidates:
            # Fallback: any available, prefer offline then speed
            fallback = self._fallback()
            if fallback is None:
                raise RuntimeError("ModelRouter: no providers registered")
            return RouteDecision(
                provider_id=fallback.provider_id,
                model_id=fallback.capability.model_id,
                score=0.0,
                capability=fallback.capability,
                reason="fallback_no_match",
            )
        candidates.sort(key=lambda t: (-t[0], t[1].capability.cost, t[1].provider_id))
        score, entry, reason = candidates[0]
        return RouteDecision(
            provider_id=entry.provider_id,
            model_id=entry.capability.model_id,
            score=score,
            capability=entry.capability,
            reason=reason,
        )

    def select_adapter(self, needs: RouteNeeds | Mapping[str, Any] | None = None) -> LLMAdapter:
        decision = self.resolve(needs)
        return self.registry.get(decision.provider_id).adapter

    def complete(
        self,
        request: LLMRequest,
        needs: RouteNeeds | Mapping[str, Any] | None = None,
    ) -> tuple[LLMResponse, RouteDecision]:
        decision = self.resolve(needs)
        adapter = self.registry.get(decision.provider_id).adapter
        # Prefer capability model_id when request.model unset
        if not request.model and decision.model_id:
            request = LLMRequest(
                system_prompt=request.system_prompt,
                messages=request.messages,
                tools=request.tools,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                model=decision.model_id,
                metadata={**dict(request.metadata), "routed_provider": decision.provider_id},
            )
        response = adapter.complete(request)
        return response, decision

    def _eligible(self, cap: ModelCapability, needs: RouteNeeds) -> tuple[bool, str]:
        if not cap.availability:
            return False, "unavailable"
        if needs.require_offline and not cap.offline:
            return False, "offline_required"
        if needs.require_streaming and not cap.streaming:
            return False, "streaming_required"
        if needs.require_tool_calling and not cap.tool_calling:
            return False, "tools_required"
        if needs.max_cost is not None and cap.cost > needs.max_cost:
            return False, "too_expensive"
        if needs.vision > 0 and cap.vision < needs.vision:
            return False, "vision_insufficient"
        return True, ""

    def _score(self, cap: ModelCapability, needs: RouteNeeds) -> tuple[float, str]:
        # Weighted coverage of requested dimensions + soft bonuses
        dims = (
            ("reasoning", needs.reasoning, cap.reasoning),
            ("coding", needs.coding, cap.coding),
            ("creativity", needs.creativity, cap.creativity),
            ("speed", needs.speed, cap.speed),
            ("context_window", needs.context_window, cap.context_window),
        )
        score = 0.0
        parts: list[str] = []
        active = 0
        for name, need, have in dims:
            if need <= 0:
                continue
            active += 1
            # reward meeting/exceeding need; penalize shortfall
            delta = have - need
            score += 10.0 + delta * 2.0
            parts.append(f"{name}:{have}>={need}")
        if active == 0:
            # general chat: prefer speed + low cost + reasoning mid
            score = cap.speed * 1.5 + cap.reasoning + (10 - cap.cost)
            parts.append("general")
        if cap.offline:
            score += 1.0
        score -= cap.cost * 0.5
        return score, "+".join(parts) if parts else "default"

    def _fallback(self) -> ProviderEntry | None:
        entries = self.registry.entries()
        if not entries:
            return None
        available = [e for e in entries if e.capability.availability]
        pool = available or entries
        pool.sort(
            key=lambda e: (
                not e.capability.offline,
                -e.capability.speed,
                e.capability.cost,
                e.provider_id,
            )
        )
        return pool[0]

    def _iter_entries(self):
        return self.registry.entries()
