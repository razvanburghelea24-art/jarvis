"""Harness fakes for not-yet-implemented spine steps."""

from __future__ import annotations

from ..engine.context_builder import ContextBuilder
from ..engine.decision_engine import DecisionEngine
from ..engine.request_validator import RequestValidator
from ..engine.response_builder import ResponseBuilder
from ..engine.state_emitter import StateEmitter

FakeRequestValidator = RequestValidator
FakeContextBuilder = ContextBuilder
FakeDecisionEngine = DecisionEngine
FakeStateEmitter = StateEmitter
FakeResponseBuilder = ResponseBuilder
