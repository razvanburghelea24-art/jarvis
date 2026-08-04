"""TDD — RequestValidator (contracts only · Harness-ready).

DoD:
  - runs in Harness
  - PASS or standardized validation errors
  - no Planner / Memory / Gateway / Desktop imports
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ConversationHarness,
    RequestValidator,
    RequestValidationError,
    RequestValidationResult,
    reset_conversation_event_journal_for_tests,
)
from src.jarvis.cora_foundation.conversation.engine.request_validator import (
    ERROR_INVALID_JSON,
    ERROR_INVALID_TYPE,
    ERROR_MISSING_FIELD,
    ERROR_UNKNOWN_VERSION,
    ERROR_WRONG_FAMILY,
    ERROR_WRONG_KIND,
)

RV_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "request_validator.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _payload(**overrides):
    base = {
        "schema_family": "cora.conversation.contracts",
        "schema_version": 1,
        "kind": "ConversationRequest",
        "request_id": "req-rv-1",
        "session_id": "sess-1",
        "workspace_id": "ws-nymods",
        "input": "ping",
        "barge_in": False,
    }
    base.update(overrides)
    return base


def test_pass_valid_request():
    result = RequestValidator().check(_payload())
    assert isinstance(result, RequestValidationResult)
    assert result.ok is True
    assert result.request is not None
    assert result.errors == ()
    assert result.request.request_id == "req-rv-1"


def test_pass_validate_returns_request():
    req = RequestValidator().validate(_payload())
    assert req.workspace_id == "ws-nymods"


def test_fail_missing_workspace():
    result = RequestValidator().check(_payload(workspace_id=""))
    assert result.ok is False
    assert result.request is None
    codes = {e.code for e in result.errors}
    assert ERROR_MISSING_FIELD in codes


def test_fail_wrong_family():
    result = RequestValidator().check(_payload(schema_family="other.family"))
    assert result.ok is False
    assert any(e.code == ERROR_WRONG_FAMILY for e in result.errors)


def test_fail_unknown_version():
    result = RequestValidator().check(_payload(schema_version=99))
    assert result.ok is False
    assert any(e.code == ERROR_UNKNOWN_VERSION for e in result.errors)


def test_fail_wrong_kind():
    result = RequestValidator().check(_payload(kind="ConversationState"))
    assert result.ok is False
    assert any(e.code == ERROR_WRONG_KIND for e in result.errors)


def test_fail_invalid_type_barge_in():
    result = RequestValidator().check(_payload(barge_in="yes"))
    assert result.ok is False
    assert any(e.code == ERROR_INVALID_TYPE for e in result.errors)


def test_fail_invalid_json_string():
    result = RequestValidator().check("{not-json")
    assert result.ok is False
    assert any(e.code == ERROR_INVALID_JSON for e in result.errors)


def test_fail_missing_request_id():
    p = _payload()
    del p["request_id"]
    result = RequestValidator().check(p)
    assert result.ok is False
    assert any(e.code == ERROR_MISSING_FIELD and e.field == "request_id" for e in result.errors)


def test_validate_raises_on_invalid():
    with pytest.raises(Exception):
        RequestValidator().validate(_payload(workspace_id=""))


def test_harness_uses_real_request_validator():
    h = ConversationHarness()
    assert isinstance(h.engine.validator, RequestValidator)
    # Not the skeleton stub path
    assert h.engine.validator.check(_payload()).ok is True
    bad = h.engine.validator.check(_payload(workspace_id=""))
    assert bad.ok is False


def test_harness_turn_with_real_validator():
    h = ConversationHarness()
    result = h.run_turn(
        {
            "request_id": "req-h-rv",
            "session_id": "sess-1",
            "workspace_id": "ws-nymods",
            "input": "hello",
        }
    )
    assert result.ok is True
    assert result.response is not None
    assert result.response.text == ""


def test_request_validator_imports_only_contracts():
    tree = ast.parse(RV_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "planner",
        "memory",
        "gateway",
        "electron",
        "react",
        "persona",
        "avatar",
        "snapshot",
        "harness",
        "openai",
        "httpx",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            if mod.startswith("."):
                assert "contracts" in mod, f"unexpected relative import {mod}"
                continue
            for bad in forbidden:
                assert bad not in mod.split("."), f"from {mod}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                low = alias.name.lower()
                for bad in forbidden:
                    assert bad not in low.split(".")


def test_error_is_standardized():
    err = RequestValidationError(code=ERROR_MISSING_FIELD, message="workspace_id required", field="workspace_id")
    d = err.to_dict()
    assert d["code"] == ERROR_MISSING_FIELD
    assert d["field"] == "workspace_id"
