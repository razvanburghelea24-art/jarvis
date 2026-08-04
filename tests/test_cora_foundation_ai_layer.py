"""TDD — OpenAI + Claude providers + ModelRouter (AI Layer sprint)."""

from __future__ import annotations

import json

import pytest

from src.jarvis.cora_foundation.llm import (
    ClaudeError,
    ClaudeProvider,
    LLMAdapter,
    LLMRequest,
    ModelCapability,
    ModelRouter,
    OpenAIError,
    OpenAIProvider,
    RouteNeeds,
    routing_test_registry,
)


def _openai_payload(text: str = "hi from gpt") -> bytes:
    return json.dumps(
        {
            "model": "gpt-4o-mini",
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
    ).encode()


def _claude_payload(text: str = "hi from claude") -> bytes:
    return json.dumps(
        {
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 4, "output_tokens": 6},
        }
    ).encode()


def test_openai_is_adapter_and_complete():
    p = OpenAIProvider(api_key="sk-test", opener=lambda u, d, t, h=None: _openai_payload("ok"))
    assert isinstance(p, LLMAdapter)
    out = p.complete(LLMRequest(messages=({"role": "user", "content": "x"},)))
    assert out.provider == "openai"
    assert out.text == "ok"
    assert out.usage["total_tokens"] == 8


def test_openai_missing_key():
    with pytest.raises(OpenAIError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key="").complete(LLMRequest(messages=({"role": "user", "content": "x"},)))


def test_claude_is_adapter_and_complete():
    p = ClaudeProvider(api_key="ant-test", opener=lambda u, d, t, h=None: _claude_payload("ok"))
    assert isinstance(p, LLMAdapter)
    out = p.complete(
        LLMRequest(system_prompt="sys", messages=({"role": "user", "content": "x"},))
    )
    assert out.provider == "claude"
    assert out.text == "ok"
    assert out.usage["total_tokens"] == 10


def test_claude_error_payload():
    p = ClaudeProvider(
        api_key="x",
        opener=lambda u, d, t, h=None: json.dumps(
            {"type": "error", "error": {"message": "nope"}}
        ).encode(),
    )
    with pytest.raises(ClaudeError, match="nope"):
        p.complete(LLMRequest(messages=({"role": "user", "content": "x"},)))


def test_extended_capability_fields():
    cap = ModelCapability(
        reasoning=9,
        coding=9,
        creativity=7,
        context_window=9,
        cost_per_1k_tokens=0.01,
        availability=True,
        provider_id="claude",
    )
    d = cap.to_dict()
    assert d["creativity"] == 7
    assert d["context_window"] == 9
    assert d["cost_per_1k_tokens"] == 0.01
    assert d["availability"] is True


def test_router_offline_prefers_ollama():
    router = ModelRouter(routing_test_registry())
    decision = router.resolve(RouteNeeds(require_offline=True, reasoning=6))
    assert decision.provider_id == "ollama"
    assert decision.capability.offline is True


def test_router_coding_prefers_claude():
    router = ModelRouter(routing_test_registry())
    decision = router.resolve(RouteNeeds(coding=9, reasoning=8))
    assert decision.provider_id == "claude"


def test_router_general_chat_picks_capable_online_or_fast():
    router = ModelRouter(routing_test_registry())
    decision = router.resolve(RouteNeeds())  # general
    assert decision.provider_id in {"ollama", "openai", "claude", "mock"}


def test_router_complete_uses_selected_provider():
    router = ModelRouter(routing_test_registry())
    resp, decision = router.complete(
        LLMRequest(messages=({"role": "user", "content": "hi"},)),
        RouteNeeds(require_offline=True),
    )
    assert decision.provider_id == "ollama"
    assert resp.provider == "ollama"
    assert resp.text == "ollama"


def test_router_never_needs_vendor_name_in_needs():
    needs = RouteNeeds.from_mapping({"coding": 9, "reasoning": 8})
    assert not hasattr(needs, "provider")
    decision = ModelRouter(routing_test_registry()).resolve(needs)
    assert decision.provider_id == "claude"
