"""TDD — OllamaProvider + ModelCapability + ProviderRegistry (Stage 2)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.llm import (
    LLMAdapter,
    LLMRequest,
    ModelCapability,
    MockLLMProvider,
    OllamaError,
    OllamaProvider,
    ProviderRegistry,
    default_dev_registry,
)


def _ollama_chat_payload(content: str = "Salut de la Ollama") -> bytes:
    return json.dumps(
        {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 8,
        }
    ).encode("utf-8")


def test_model_capability_clamped_and_json():
    cap = ModelCapability(
        reasoning=99, coding=-3, offline=True, provider_id="ollama", model_id="x"
    )
    assert cap.reasoning == 10
    assert cap.coding == 0
    assert cap.offline is True
    assert cap.to_dict()["provider_id"] == "ollama"


def test_ollama_is_llm_adapter():
    provider = OllamaProvider(opener=lambda url, data, timeout: _ollama_chat_payload())
    assert isinstance(provider, LLMAdapter)
    assert provider.provider_id == "ollama"
    assert provider.capability.offline is True


def test_ollama_complete_via_injected_opener():
    provider = OllamaProvider(
        model="llama3.2",
        opener=lambda url, data, timeout: _ollama_chat_payload("ok offline"),
    )
    out = provider.complete(
        LLMRequest(
            system_prompt="You are Cora",
            messages=({"role": "user", "content": "salut"},),
            temperature=0.1,
            max_tokens=64,
        )
    )
    assert out.provider == "ollama"
    assert out.text == "ok offline"
    assert out.finish_reason == "stop"
    assert out.usage["total_tokens"] == 20
    assert out.model == "llama3.2"


def test_ollama_builds_system_and_user_messages():
    captured: dict = {}

    def opener(url, data, timeout):
        captured["url"] = url
        captured["body"] = json.loads(data.decode("utf-8"))
        return _ollama_chat_payload()

    OllamaProvider(base_url="http://127.0.0.1:11434", opener=opener).complete(
        LLMRequest(system_prompt="SYS", messages=({"role": "user", "content": "hi"},))
    )
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["stream"] is False
    assert captured["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert captured["body"]["messages"][1]["content"] == "hi"


def test_ollama_error_payload_raises():
    provider = OllamaProvider(
        opener=lambda url, data, timeout: json.dumps({"error": "model not found"}).encode()
    )
    with pytest.raises(OllamaError, match="model not found"):
        provider.complete(LLMRequest(messages=({"role": "user", "content": "x"},)))


def test_registry_mock_and_ollama():
    reg = default_dev_registry()
    assert "mock" in reg.ids()
    assert "ollama" in reg.ids()
    assert reg.get("ollama").capability.offline is True
    assert reg.get("mock").adapter.provider_id == "mock"
    caps = {c.provider_id for c in reg.capabilities()}
    assert caps == {"mock", "ollama"}


def test_registry_complete_through_ollama_entry():
    reg = ProviderRegistry()
    ollama = OllamaProvider(opener=lambda u, d, t: _ollama_chat_payload("via registry"))
    reg.register(ollama, ollama.capability)
    entry = reg.get("ollama")
    out = entry.adapter.complete(LLMRequest(messages=({"role": "user", "content": "q"},)))
    assert out.text == "via registry"


def test_mock_still_works_alongside_ollama():
    assert (
        MockLLMProvider()
        .complete(LLMRequest(messages=({"role": "user", "content": "x"},)))
        .provider
        == "mock"
    )
