"""Provider registry — adapters + ModelCapability (Router input later)."""

from __future__ import annotations

from dataclasses import dataclass

from .adapter import LLMAdapter
from .capabilities import CAPABILITY_MOCK, CAPABILITY_OLLAMA_DEFAULT, ModelCapability
from .mock import MockLLMProvider
from .ollama import OllamaProvider


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
        if adapter.provider_id != capability.provider_id and capability.provider_id:
            # allow capability.provider_id empty → fill from adapter
            pass
        cap = capability
        if not cap.provider_id:
            cap = ModelCapability(
                reasoning=cap.reasoning,
                coding=cap.coding,
                vision=cap.vision,
                speed=cap.speed,
                offline=cap.offline,
                streaming=cap.streaming,
                tool_calling=cap.tool_calling,
                cost=cap.cost,
                provider_id=adapter.provider_id,
                model_id=cap.model_id,
            )
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


def default_dev_registry(
    *,
    ollama_model: str = "llama3.2",
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> ProviderRegistry:
    """Dev default: Mock + Ollama (Ollama = offline default for real calls)."""
    reg = ProviderRegistry()
    mock = MockLLMProvider()
    reg.register(mock, CAPABILITY_MOCK)
    ollama = OllamaProvider(model=ollama_model, base_url=ollama_base_url)
    reg.register(
        ollama,
        ModelCapability(
            **{
                **CAPABILITY_OLLAMA_DEFAULT.to_dict(),
                "model_id": ollama_model,
                "provider_id": "ollama",
            }
        ),
    )
    return reg
