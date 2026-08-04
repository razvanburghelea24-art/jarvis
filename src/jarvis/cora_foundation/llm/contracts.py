"""LLM contracts v1 — provider-agnostic request/response.

Family is separate from conversation contracts. Providers implement the same shapes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

SCHEMA_FAMILY = "cora.llm.contracts"
SCHEMA_VERSION = 1
SCHEMA_ID = f"{SCHEMA_FAMILY}.v{SCHEMA_VERSION}"

KIND_REQUEST = "LLMRequest"
KIND_RESPONSE = "LLMResponse"


def freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if data is None:
        return MappingProxyType({})
    return MappingProxyType(dict(data))


def freeze_messages(messages: Sequence[Mapping[str, Any]] | None) -> tuple[Mapping[str, Any], ...]:
    if not messages:
        return ()
    return tuple(MappingProxyType(dict(m)) for m in messages)


@dataclass(frozen=True)
class LLMRequest:
    """Canonical LLM call input — no provider fields."""

    system_prompt: str = ""
    messages: tuple[Mapping[str, Any], ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    temperature: float = 0.2
    max_tokens: int = 1024
    model: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", freeze_messages(self.messages))
        object.__setattr__(self, "tools", freeze_messages(self.tools))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        object.__setattr__(self, "temperature", float(self.temperature))
        object.__setattr__(self, "max_tokens", int(self.max_tokens))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_REQUEST,
            "system_prompt": self.system_prompt,
            "messages": [dict(m) for m in self.messages],
            "tools": [dict(t) for t in self.tools],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "model": self.model,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class LLMResponse:
    """Canonical LLM call output — no provider fields."""

    text: str = ""
    finish_reason: str = "stop"
    usage: Mapping[str, Any] = None  # type: ignore[assignment]
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    model: str | None = None
    provider: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", freeze_mapping(self.usage))
        object.__setattr__(self, "tool_calls", freeze_messages(self.tool_calls))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_RESPONSE,
            "text": self.text,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "tool_calls": [dict(t) for t in self.tool_calls],
            "model": self.model,
            "provider": self.provider,
            "metadata": dict(self.metadata),
        }


def dumps_canonical(obj: Mapping[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
