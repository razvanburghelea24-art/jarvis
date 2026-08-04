"""TDD — LLM Adapter Stage 1 (contracts · protocol · Mock provider)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import ContextBuilder, RequestValidator
from src.jarvis.cora_foundation.llm import (
    SCHEMA_FAMILY,
    LLMAdapter,
    LLMRequest,
    LLMResponse,
    MockLLMProvider,
    build_llm_request,
    dumps_canonical,
)

LLM_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "llm"
)


def _ctx_pair(text: str = "salut Cora"):
    req = RequestValidator().validate(
        {
            "request_id": "req-llm-1",
            "session_id": "sess-llm",
            "workspace_id": "ws-nymods",
            "input": text,
        }
    )
    ctx = ContextBuilder().build(req)
    return req, ctx


def test_llm_request_response_contracts_json_immutable():
    req = LLMRequest(
        system_prompt="sys",
        messages=({"role": "user", "content": "hi"},),
        temperature=0.1,
        max_tokens=64,
        metadata={"k": "v"},
    )
    raw = req.to_canonical_dict()
    assert raw["schema_family"] == SCHEMA_FAMILY
    assert raw["kind"] == "LLMRequest"
    assert json.loads(dumps_canonical(raw))["messages"][0]["content"] == "hi"
    with pytest.raises(Exception):
        req.system_prompt = "x"  # type: ignore[misc]

    resp = LLMResponse(text="hello", finish_reason="stop", usage={"total_tokens": 3}, provider="mock")
    rraw = resp.to_canonical_dict()
    assert rraw["kind"] == "LLMResponse"
    assert rraw["text"] == "hello"
    with pytest.raises(Exception):
        resp.text = "mut"  # type: ignore[misc]


def test_mock_provider_is_llm_adapter():
    mock = MockLLMProvider()
    assert isinstance(mock, LLMAdapter)
    assert mock.provider_id == "mock"
    out = mock.complete(
        LLMRequest(messages=({"role": "user", "content": "status"},))
    )
    assert isinstance(out, LLMResponse)
    assert out.provider == "mock"
    assert "status" in out.text
    assert out.finish_reason == "stop"
    assert out.usage.get("total_tokens", 0) > 0


def test_context_to_llm_request_to_mock_response():
    conv_req, ctx = _ctx_pair("cum stă NyMods?")
    llm_req = build_llm_request(conv_req, ctx)
    assert llm_req.messages[0]["content"] == "cum stă NyMods?"
    assert llm_req.metadata["request_id"] == "req-llm-1"
    assert "Cora" in llm_req.system_prompt
    out = MockLLMProvider().complete(llm_req)
    assert "cum stă NyMods?" in out.text
    assert out.model == "mock-v1"


def test_mock_empty_user_message():
    out = MockLLMProvider(prefix="").complete(LLMRequest(messages=()))
    assert out.text == ""
    assert out.finish_reason == "stop"


def test_no_external_http_sdks_in_llm_package():
    """Forbid vendor SDKs; local relative modules (openai_provider) are OK."""
    forbidden_roots = {"openai", "anthropic", "httpx", "requests", "google"}
    for path in LLM_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # package-local relative import
                mod = (node.module or "").lower()
                root = mod.split(".", 1)[0]
                assert root not in forbidden_roots, f"{path.name} imports {mod}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.lower().split(".", 1)[0]
                    assert root not in forbidden_roots, f"{path.name} imports {alias.name}"


def test_tools_field_present_but_unused():
    req = LLMRequest(tools=({"name": "search"},), messages=({"role": "user", "content": "x"},))
    out = MockLLMProvider().complete(req)
    assert out.tool_calls == ()
