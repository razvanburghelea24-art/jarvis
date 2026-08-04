"""LLMAdapter — sole Core surface that talks to a model provider.

Conversation Engine Core v1 does not import providers.
Router (later) selects which adapter instance to use.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import LLMRequest, LLMResponse


@runtime_checkable
class LLMAdapter(Protocol):
    """Provider-agnostic complete() contract."""

    @property
    def provider_id(self) -> str:
        """Stable id: mock | ollama | openai | claude | gemini | deepseek …"""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one non-streaming completion. Streaming providers come later."""
