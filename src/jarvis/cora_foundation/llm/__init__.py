"""cora_foundation.llm — One LLM Interface · Many Providers + Model Router."""

from .adapter import LLMAdapter
from .capabilities import (
    CAPABILITY_CLAUDE_DEFAULT,
    CAPABILITY_MOCK,
    CAPABILITY_OLLAMA_DEFAULT,
    CAPABILITY_OPENAI_DEFAULT,
    ModelCapability,
)
from .claude_provider import ClaudeError, ClaudeProvider
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
from .openai_provider import OpenAIError, OpenAIProvider
from .registry import (
    ProviderEntry,
    ProviderRegistry,
    default_dev_registry,
    full_provider_registry,
    routing_test_registry,
)
from .router import ModelRouter, RouteDecision, RouteNeeds

__all__ = [
    "CAPABILITY_CLAUDE_DEFAULT",
    "CAPABILITY_MOCK",
    "CAPABILITY_OLLAMA_DEFAULT",
    "CAPABILITY_OPENAI_DEFAULT",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_SYSTEM",
    "KIND_REQUEST",
    "KIND_RESPONSE",
    "ClaudeError",
    "ClaudeProvider",
    "LLMAdapter",
    "LLMRequest",
    "LLMResponse",
    "ModelCapability",
    "ModelRouter",
    "MockLLMProvider",
    "OllamaError",
    "OllamaProvider",
    "OpenAIError",
    "OpenAIProvider",
    "ProviderEntry",
    "ProviderRegistry",
    "RouteDecision",
    "RouteNeeds",
    "SCHEMA_FAMILY",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "as_adapter",
    "build_llm_request",
    "default_dev_registry",
    "dumps_canonical",
    "full_provider_registry",
    "routing_test_registry",
]
