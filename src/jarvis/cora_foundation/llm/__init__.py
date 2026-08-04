"""cora_foundation.llm — LLM Adapter layer (post Conversation Engine Core v1).

Stage 1 ✅: contracts + protocol + Mock
Stage 2: Ollama (first real) + ModelCapability + registry · more providers next
Stage 3: Model Router (capability-based)

One LLM Interface · Many Providers
Never: Planner Routing · Tool Routing · 6B · Electron · Persona.
"""

from .adapter import LLMAdapter
from .capabilities import (
    CAPABILITY_MOCK,
    CAPABILITY_OLLAMA_DEFAULT,
    ModelCapability,
)
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
from .ollama import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaError, OllamaProvider
from .registry import ProviderEntry, ProviderRegistry, default_dev_registry

__all__ = [
    "CAPABILITY_MOCK",
    "CAPABILITY_OLLAMA_DEFAULT",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_SYSTEM",
    "KIND_REQUEST",
    "KIND_RESPONSE",
    "LLMAdapter",
    "LLMRequest",
    "LLMResponse",
    "ModelCapability",
    "MockLLMProvider",
    "OllamaError",
    "OllamaProvider",
    "ProviderEntry",
    "ProviderRegistry",
    "SCHEMA_FAMILY",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "as_adapter",
    "build_llm_request",
    "default_dev_registry",
    "dumps_canonical",
]
