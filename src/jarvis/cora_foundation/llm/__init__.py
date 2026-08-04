"""cora_foundation.llm — LLM Adapter layer (post Conversation Engine Core v1).

Stage 1: contracts + adapter protocol + Mock provider.
Stage 2: real providers (Ollama, OpenAI, Claude, Gemini, DeepSeek).
Stage 3: Model Router.

Never: Planner Routing · Tool Routing · 6B · Electron · Persona.
"""

from .adapter import LLMAdapter
from .contracts import (
    KIND_REQUEST,
    KIND_RESPONSE,
    SCHEMA_FAMILY,
    SCHEMA_ID,
    SCHEMA_VERSION,
    LLMRequest,
    LLMResponse,
    dumps_canonical,
)
from .from_context import DEFAULT_SYSTEM, build_llm_request
from .mock import MockLLMProvider, as_adapter

__all__ = [
    "DEFAULT_SYSTEM",
    "KIND_REQUEST",
    "KIND_RESPONSE",
    "LLMAdapter",
    "LLMRequest",
    "LLMResponse",
    "MockLLMProvider",
    "SCHEMA_FAMILY",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "as_adapter",
    "build_llm_request",
    "dumps_canonical",
]
