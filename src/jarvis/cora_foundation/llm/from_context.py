"""Build LLMRequest from conversation Context / Request (no provider knowledge)."""

from __future__ import annotations

from typing import Any, Mapping

from ..conversation.contracts import ConversationContext, ConversationRequest
from .contracts import LLMRequest

DEFAULT_SYSTEM = (
    "You are Cora, the NyMods assistant. Be concise, accurate, and Owner-safe. "
    "Do not invent tool executions."
)


def build_llm_request(
    request: ConversationRequest,
    context: ConversationContext,
    *,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> LLMRequest:
    """Context → LLMRequest. Does not call any model."""
    meta = {
        "request_id": request.request_id,
        "session_id": request.session_id,
        "workspace_id": request.workspace_id,
        "context_workspace": context.workspace_id,
    }
    if metadata:
        meta.update(dict(metadata))
    return LLMRequest(
        system_prompt=system_prompt if system_prompt is not None else DEFAULT_SYSTEM,
        messages=({"role": "user", "content": request.input or ""},),
        tools=(),
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        metadata=meta,
    )
