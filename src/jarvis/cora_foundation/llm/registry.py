"""Provider registry — adapters + ModelCapability (Router input)."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from .adapter import LLMAdapter
from .capabilities import (
    CAPABILITY_CLAUDE_DEFAULT,
    CAPABILITY_MOCK,
    CAPABILITY_OLLAMA_DEFAULT,
    CAPABILITY_OPENAI_DEFAULT,
    ModelCapability,
)
from .claude_provider import ClaudeProvider
from .mock import MockLLMProvider
from .ollama import OllamaProvider
from .openai_provider import OpenAIProvider


@dataclass(frozen=True)
class ProviderEntry:
    adapter: LLMAdapter
    capability: ModelCapability

    @property
    def provider_id(self) -> str:
        return self.adapter.provider_id


class ProviderRegistry:
    """One LLM Interface · Many Providers."""

    def __init__(self) -> None:
        self._entries: dict[str, ProviderEntry] = {}

    def register(self, adapter: LLMAdapter, capability: ModelCapability) -> None:
        cap = capability
        if not cap.provider_id:
            cap = replace(cap, provider_id=adapter.provider_id)
        self._entries[adapter.provider_id] = ProviderEntry(adapter=adapter, capability=cap)

    def get(self, provider_id: str) -> ProviderEntry:
        try:
            return self._entries[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {provider_id!r}") from exc

    def ids(self) -> list[str]:
        return sorted(self._entries)

    def capabilities(self) -> list[ModelCapability]:
        return [e.capability for e in self._entries.values()]

    def entries(self) -> list[ProviderEntry]:
        return list(self._entries.values())


def default_dev_registry(
    *,
    ollama_model: str = "llama3.2",
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> ProviderRegistry:
    """Dev default: Mock + Ollama."""
    reg = ProviderRegistry()
    mock = MockLLMProvider()
    reg.register(mock, CAPABILITY_MOCK)
    ollama = OllamaProvider(model=ollama_model, base_url=ollama_base_url)
    reg.register(
        ollama,
        replace(CAPABILITY_OLLAMA_DEFAULT, model_id=ollama_model, provider_id="ollama"),
    )
    return reg


def routing_test_registry() -> ProviderRegistry:
    """Mock + Ollama + OpenAI + Claude with injectable openers (Router tests)."""

    def ollama_ok(url, data, timeout):
        return json.dumps(
            {
                "model": "llama3.2",
                "message": {"role": "assistant", "content": "ollama"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 1,
                "eval_count": 1,
            }
        ).encode()

    def openai_ok(url, data, timeout, headers=None):
        return json.dumps(
            {
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "openai"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()

    def claude_ok(url, data, timeout, headers=None):
        return json.dumps(
            {
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "claude"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ).encode()

    reg = ProviderRegistry()
    reg.register(MockLLMProvider(), CAPABILITY_MOCK)
    ollama = OllamaProvider(opener=ollama_ok)
    reg.register(ollama, replace(CAPABILITY_OLLAMA_DEFAULT, availability=True))
    openai = OpenAIProvider(api_key="test", opener=openai_ok)
    reg.register(openai, replace(CAPABILITY_OPENAI_DEFAULT, availability=True))
    claude = ClaudeProvider(api_key="test", opener=claude_ok)
    reg.register(claude, replace(CAPABILITY_CLAUDE_DEFAULT, availability=True))
    return reg


def full_provider_registry(**kwargs) -> ProviderRegistry:
    """Alias — full set for routing / integration tests."""
    return routing_test_registry()
