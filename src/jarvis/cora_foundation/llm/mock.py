"""MockLLMProvider — deterministic LLMAdapter for tests / Harness.

No network. No API keys. Stable text from the last user message.
"""

from __future__ import annotations

from .adapter import LLMAdapter
from .contracts import LLMRequest, LLMResponse


class MockLLMProvider:
    """Implements LLMAdapter without contacting any remote model."""

    provider_id = "mock"

    def __init__(self, *, prefix: str = "[mock] ") -> None:
        self._prefix = prefix

    def complete(self, request: LLMRequest) -> LLMResponse:
        user_text = ""
        for msg in reversed(request.messages):
            if str(msg.get("role") or "") == "user":
                user_text = str(msg.get("content") or "")
                break
        if not user_text and request.system_prompt:
            user_text = "(no user message)"
        text = f"{self._prefix}{user_text}".strip()
        prompt_tokens = max(1, len(request.system_prompt) // 4 + sum(len(str(m)) for m in request.messages) // 4)
        completion_tokens = max(1, len(text) // 4)
        return LLMResponse(
            text=text,
            finish_reason="stop",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            tool_calls=(),
            model=request.model or "mock-v1",
            provider=self.provider_id,
            metadata={"adapter": "MockLLMProvider"},
        )


def as_adapter(provider: MockLLMProvider) -> LLMAdapter:
    """Type helper — MockLLMProvider satisfies LLMAdapter."""
    return provider
